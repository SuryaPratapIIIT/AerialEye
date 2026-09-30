import { useState } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { Eye, Search, Activity, Layers, CheckSquare, HardDrive, Menu, X, ArrowUpRight } from 'lucide-react'

const NAV_ITEMS = [
  { to: '/search', label: 'Discover', icon: Search },
  { to: '/analyze', label: 'Analyze', icon: Activity },
  { to: '/similar-sites', label: 'Correlate', icon: Layers },
  { to: '/detect', label: 'ML Detect', icon: CheckSquare },
  { to: '/review', label: 'Verify', icon: CheckSquare },
  { to: '/data', label: 'Data', icon: HardDrive },
]

export default function Navbar() {
  const navigate = useNavigate()
  const location = useLocation()
  const [mobileOpen, setMobileOpen] = useState(false)

  return (
    <motion.nav 
      initial={{ y: -100, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.5, ease: "easeOut" }}
      className="fixed top-4 left-1/2 -translate-x-1/2 z-50 w-[95%] max-w-5xl rounded-2xl border border-slate-700/50 bg-slate-900/60 shadow-2xl shadow-cyan-900/20 backdrop-blur-md"
    >
      <div className="px-4 h-14 flex items-center justify-between gap-4">
        {/* Logo */}
        <button
          onClick={() => navigate('/')}
          className="flex items-center gap-3 shrink-0 group"
        >
          <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-cyan-600 to-blue-500 flex items-center justify-center shadow-[0_0_15px_rgba(6,182,212,0.4)] group-hover:shadow-[0_0_25px_rgba(6,182,212,0.6)] transition-all duration-300 relative overflow-hidden">
             <div className="absolute inset-0 bg-white/20 blur-sm translate-y-full group-hover:translate-y-0 transition-transform duration-500" />
            <Eye className="w-5 h-5 text-white relative z-10" />
          </div>
          <span className="font-display font-bold text-slate-100 text-lg tracking-wide hidden sm:block">
            AERIAL<span className="text-cyan-400">EYE</span>
          </span>
        </button>

        {/* Primary nav — desktop */}
        <div className="hidden md:flex items-center gap-2">
          {NAV_ITEMS.map(({ to, label, icon: Icon }) => {
            const isActive = location.pathname.startsWith(to)
            return (
              <NavLink
                key={to}
                to={to}
                className="relative px-3 py-1.5 rounded-lg text-sm font-medium transition-all duration-300 flex items-center gap-2 group"
              >
                <Icon className={`w-4 h-4 transition-colors ${isActive ? 'text-cyan-400' : 'text-slate-400 group-hover:text-cyan-300'}`} />
                <span className={`relative z-10 transition-colors ${isActive ? 'text-cyan-50' : 'text-slate-400 group-hover:text-slate-200'}`}>
                  {label}
                </span>
                
                {isActive && (
                  <motion.div
                    layoutId="navbar-indicator"
                    className="absolute inset-0 bg-cyan-500/10 rounded-lg border border-cyan-500/20 shadow-[inset_0_0_10px_rgba(6,182,212,0.1)]"
                    transition={{ type: "spring", bounce: 0.2, duration: 0.6 }}
                  />
                )}
              </NavLink>
            )
          })}
        </div>

        {/* Action Button & Mobile Toggle */}
        <div className="flex items-center gap-3">

          <button
            className="md:hidden p-2 rounded-lg text-slate-400 hover:text-cyan-400 hover:bg-slate-800/50 transition-colors focus:outline-none"
            onClick={() => setMobileOpen((v) => !v)}
            aria-label="Toggle menu"
          >
            {mobileOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
        </div>
      </div>

      {/* Mobile menu */}
      <AnimatePresence>
        {mobileOpen && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="md:hidden border-t border-slate-700/50 bg-slate-900/90 backdrop-blur-xl overflow-hidden rounded-b-2xl"
          >
            <div className="px-4 py-4 flex flex-col gap-2">
              {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
                <NavLink
                  key={to}
                  to={to}
                  onClick={() => setMobileOpen(false)}
                  className={({ isActive }) =>
                    `flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-colors border ${
                      isActive
                        ? 'bg-cyan-500/10 border-cyan-500/30 text-cyan-400 shadow-[0_0_10px_rgba(6,182,212,0.1)]'
                        : 'border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-800'
                    }`
                  }
                >
                  <Icon className="w-5 h-5" />
                  {label}
                </NavLink>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.nav>
  )
}
