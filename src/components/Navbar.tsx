import { useState, useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { Satellite, Menu, X } from 'lucide-react'

const navLinks = [
  { name: 'Detect', path: '/detect' },
  // { name: 'GIS Map', path: '/gis' },
]

export default function Navbar() {
  const [isOpen, setIsOpen] = useState(false)
  const [scrolled, setScrolled] = useState(false)
  const location = useLocation()

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  useEffect(() => {
    setIsOpen(false)
  }, [location])

  return (
    <nav
      className={`fixed top-0 left-0 right-0 z-50 transition-all duration-200 ${scrolled
          ? 'bg-white/90 backdrop-blur-md border-b border-stone-200 shadow-soft'
          : 'bg-white/70 backdrop-blur-sm border-b border-transparent'
        }`}
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo */}
          <Link to="/" className="flex items-center gap-2.5 group shrink-0">
            <motion.div
              className="w-9 h-9 rounded-lg bg-teal-600 flex items-center justify-center shadow-soft"
              whileHover={{ scale: 1.05, rotate: 5 }}
              whileTap={{ scale: 0.95 }}
            >
              <Satellite className="w-4.5 h-4.5 text-white" strokeWidth={2.2} />
            </motion.div>
            <span className="font-['Space_Grotesk'] font-semibold text-lg text-stone-900 tracking-tight">
              Aerial<span className="text-teal-600">Eye</span>
            </span>
          </Link>

          {/* Desktop Nav */}
          <div className="hidden md:flex items-center gap-1">
            {navLinks.map((link) => (
              <Link
                key={link.path}
                to={link.path}
                className="relative px-4 py-2 rounded-lg"
              >
                <span
                  className={`relative z-10 text-sm font-medium transition-colors ${location.pathname === link.path
                      ? 'text-teal-700'
                      : 'text-stone-600 hover:text-stone-900'
                    }`}
                >
                  {link.name}
                </span>
                {location.pathname === link.path && (
                  <motion.div
                    layoutId="navbar-indicator"
                    className="absolute inset-0 bg-teal-50 rounded-lg"
                    transition={{ type: 'spring', duration: 0.5, bounce: 0.2 }}
                  />
                )}
              </Link>
            ))}
          </div>

          {/* Badge */}
          <div className="hidden lg:flex items-center">
            <div className="px-3 py-1.5 rounded-full bg-amber-50 border border-amber-200">
              <span className="text-xs font-medium text-amber-800 tracking-wide">
                Indian Railways × DIGIT
              </span>
            </div>
          </div>

          {/* Mobile Menu Button */}
          <button
            className="md:hidden p-2 text-stone-700 hover:bg-stone-100 rounded-lg transition-colors"
            onClick={() => setIsOpen(!isOpen)}
            aria-label="Toggle menu"
          >
            {isOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
        </div>
      </div>

      {/* Mobile Menu */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="md:hidden overflow-hidden bg-white border-t border-stone-200"
          >
            <div className="px-4 py-3 space-y-1">
              {navLinks.map((link) => (
                <Link
                  key={link.path}
                  to={link.path}
                  className={`block py-2.5 px-3 rounded-lg transition-colors text-sm font-medium ${location.pathname === link.path
                      ? 'bg-teal-50 text-teal-700'
                      : 'text-stone-700 hover:bg-stone-50'
                    }`}
                >
                  {link.name}
                </Link>
              ))}
              <div className="pt-2 mt-2 border-t border-stone-100">
                <div className="px-3 py-1.5 rounded-full bg-amber-50 border border-amber-200 inline-block">
                  <span className="text-xs font-medium text-amber-800">
                    Indian Railways × DIGIT
                  </span>
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </nav>
  )
}
