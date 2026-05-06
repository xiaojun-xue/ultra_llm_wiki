# 模块设计 - 认证授权 (Auth)

## 1. 模块概述

认证授权模块提供用户管理和 API 访问控制。

### 1.1 组件

| 文件 | 职责 |
|------|------|
| `core/auth.py` | JWT 工具函数、密码哈希 |
| `middleware/auth.py` | FastAPI 依赖注入 |
| `models/user.py` | User SQLAlchemy 模型 |
| `api/auth.py` | 注册/登录/登出 API |

---

## 2. 数据模型

```python
class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(20), default="external")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_login_at: Mapped[datetime | None]
```

### 2.1 角色枚举

```python
ROLE_ADMIN = "admin"      # 管理员
ROLE_INTERNAL = "internal" # 内部用户
ROLE_EXTERNAL = "external" # 外部用户
```

---

## 3. JWT 认证

### 3.1 Token 结构

```python
# core/auth.py
def create_access_token(user_id: str, role: str, email: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": user_id,
        "role": role,
        "email": email,
        "exp": expire,
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None
```

### 3.2 密码处理

```python
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)
```

---

## 4. 中间件/依赖注入

### 4.1 get_current_user

```python
# middleware/auth.py
security = HTTPBearer(auto_error=False)

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(401, "Not authenticated")

    payload = decode_token(credentials.credentials)
    if payload is None:
        raise HTTPException(401, "Invalid or expired token")

    user = await db.get(User, payload["sub"])
    if not user or not user.is_active:
        raise HTTPException(403, "User account is disabled")

    return user
```

### 4.2 require_role

```python
def require_role(allowed_roles: list[str]):
    async def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(403, f"Requires: {', '.join(allowed_roles)}")
        return user
    return checker

# 使用
@router.delete("/{doc_id}")
async def delete_doc(
    doc_id: str,
    user: User = Depends(require_role(["admin", "internal"]))
):
    ...
```

### 4.3 类型别名

```python
AuthenticatedUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(require_role(["admin"]))]
InternalUser = Annotated[User, Depends(require_role(["admin", "internal"]))]
```

---

## 5. API 路由

### 5.1 /api/auth/register

```
POST /api/auth/register
Body: {"email": "...", "password": "...", "name": "...", "role": "external"}
Response: {"access_token": "...", "user": {...}}
```

### 5.2 /api/auth/login

```
POST /api/auth/login
Body: {"email": "...", "password": "..."}
Response: {"access_token": "...", "user": {...}}
```

### 5.3 /api/auth/me

```
GET /api/auth/me
Headers: Authorization: Bearer <token>
Response: {"id": "...", "email": "...", "name": "...", "role": "..."}
```

---

## 6. 前端 Auth

### 6.1 AuthContext

```typescript
// lib/auth.tsx
interface AuthContext {
  user: User | null;
  token: string | null;
  login: (email, password) => Promise<void>;
  register: (email, password, name) => Promise<void>;
  logout: () => void;
}
```

### 6.2 Token 同步

```typescript
// 登录后同步到 Cookie (供 middleware 读取)
setTokenCookie(token);

// 登出后清除
removeTokenCookie();
```

---

## 7. 权限矩阵

| 操作 | Admin | Internal | External |
|------|:-----:|:--------:|:--------:|
| 读所有文档 | ✅ | ✅ | ❌ |
| 上传 | ✅ | ✅ | ❌ |
| 删除自己文档 | ✅ | ✅ | ❌ |
| 删除任意文档 | ✅ | ❌ | ❌ |
| 管理用户 | ✅ | ❌ | ❌ |

---

*文档版本: v1.0*
