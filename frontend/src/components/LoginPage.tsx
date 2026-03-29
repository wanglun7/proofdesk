import { useState } from 'react'
import { Layers } from 'lucide-react'
import { login } from '../api'

export default function LoginPage({ onLogin }: { onLogin: () => void }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const r = await login(username, password)
      if (r.data.is_superadmin) {
        setError('Admin account is bootstrap-only. Sign in with a workspace owner/member account.')
        return
      }
      localStorage.setItem('token', r.data.access_token)
      onLogin()
    } catch {
      setError('Invalid username or password')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex w-full h-screen">
      {/* Left — brand panel */}
      <div className="hidden md:flex flex-col justify-between w-1/2 bg-slate-900 px-12 py-12">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center w-8 h-8 bg-brand-600 rounded-lg">
            <Layers size={16} className="text-white" />
          </div>
          <span className="text-white font-semibold text-[16px] tracking-tight">Proofdesk</span>
        </div>

        <div>
          <p className="text-slate-300 text-[22px] font-semibold leading-snug max-w-xs">
            Turn vendor questionnaires into delivered answers — in minutes.
          </p>
          <p className="mt-4 text-slate-500 text-sm leading-relaxed max-w-xs">
            AI-powered compliance workbench that reads your knowledge base and drafts accurate answers at scale.
          </p>
        </div>

        <p className="text-slate-600 text-xs">© 2025 Proofdesk</p>
      </div>

      {/* Right — login form */}
      <div className="flex flex-col items-center justify-center flex-1 bg-white px-8">
        <div className="w-full max-w-sm">
          {/* Mobile logo */}
          <div className="flex items-center gap-2.5 mb-8 md:hidden">
            <div className="flex items-center justify-center w-7 h-7 bg-brand-600 rounded-md">
              <Layers size={14} className="text-white" />
            </div>
            <span className="font-semibold text-slate-900 text-[15px]">Proofdesk</span>
          </div>

          <h2 className="text-xl font-semibold text-slate-900 mb-1">Sign in</h2>
          <p className="text-sm text-slate-500 mb-7">Enter your credentials to continue</p>

          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-slate-700">Username</label>
              <input
                type="text"
                value={username}
                onChange={e => setUsername(e.target.value)}
                autoFocus
                className="px-3 py-2.5 border border-slate-200 rounded-md text-sm outline-none focus:ring-2 focus:ring-brand-600/20 focus:border-brand-500 transition-colors"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-slate-700">Password</label>
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                className="px-3 py-2.5 border border-slate-200 rounded-md text-sm outline-none focus:ring-2 focus:ring-brand-600/20 focus:border-brand-500 transition-colors"
              />
            </div>

            {error && (
              <div className="text-sm text-red-600 bg-red-50 border border-red-100 px-3 py-2 rounded-md">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading || !username || !password}
              className="mt-1 py-2.5 bg-brand-600 text-white rounded-md text-sm font-semibold hover:bg-brand-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? 'Signing in…' : 'Sign in'}
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}
