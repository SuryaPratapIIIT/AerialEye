import { useEffect } from 'react'
import { Routes, Route, useLocation } from 'react-router-dom'
import { AnimatePresence } from 'framer-motion'
import Navbar from './components/Navbar'
import Landing from './pages/Landing'
import Detect from './pages/Detect'
import GIS from './pages/GIS'
import { pingBackendHealth } from './utils/api'

function App() {
  const location = useLocation()

  useEffect(() => {
    // Pre-warm Hugging Face Space backend if sleeping
    pingBackendHealth()
  }, [])

  return (
    <div className="min-h-screen bg-[#fafaf9] text-stone-900">
      <Navbar />
      <AnimatePresence mode="wait">
        <Routes location={location} key={location.pathname}>
          <Route path="/" element={<Landing />} />
          <Route path="/detect" element={<Detect />} />
          <Route path="/gis" element={<GIS />} />
        </Routes>
      </AnimatePresence>
    </div>
  )
}

export default App
