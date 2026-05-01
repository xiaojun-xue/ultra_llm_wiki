import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "LLM Wiki",
  description: "Knowledge base for source code, documents, and schematics",
};

function NavLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <Link
      href={href}
      className="px-3 py-2 rounded-md text-sm font-medium text-slate-300 hover:text-white hover:bg-slate-700 transition-colors"
    >
      {children}
    </Link>
  );
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body className="min-h-screen bg-slate-50">
        {/* Navigation */}
        <nav className="bg-slate-900 shadow-lg">
          <div className="max-w-7xl mx-auto px-4">
            <div className="flex items-center justify-between h-14">
              <Link href="/" className="flex items-center space-x-2">
                <span className="text-xl font-bold text-white">LLM Wiki</span>
                <span className="text-xs bg-blue-500 text-white px-2 py-0.5 rounded-full">
                  Knowledge Base
                </span>
              </Link>
              <div className="flex items-center space-x-1">
                <NavLink href="/">Home</NavLink>
                <NavLink href="/search">Search</NavLink>
                <NavLink href="/graph">Graph</NavLink>
                <NavLink href="/upload">Upload</NavLink>
              </div>
            </div>
          </div>
        </nav>

        {/* Main content */}
        <main className="max-w-7xl mx-auto px-4 py-6">{children}</main>
      </body>
    </html>
  );
}
