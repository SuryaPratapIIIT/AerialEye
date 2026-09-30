import { Routes, Route, useLocation } from 'react-router-dom'
import { AnimatePresence } from 'framer-motion'
import { useEffect } from 'react'
import Navbar from './components/Navbar'
import Landing from './pages/Landing'
import Detect from './pages/Detect'
import GIS from './pages/GIS'
import Search from './pages/Search'
import Analyze from './pages/Analyze'
import Review from './pages/Review'
import SimilarSites from './pages/SimilarSites'
import Data from './pages/Data'
import { pingBackendHealth } from './utils/api'

function App() {
  const location = useLocation()

  useEffect(() => {
    pingBackendHealth()
  }, [])

  return (
    <div className="min-h-screen bg-[#0a0d14] text-slate-100">
      <Navbar />
      <AnimatePresence mode="wait">
        <Routes location={location} key={location.pathname}>
          <Route path="/" element={<Landing />} />
          <Route path="/search" element={<Search />} />
          <Route path="/analyze" element={<Analyze />} />
          <Route path="/analyze/:assetId" element={<Analyze />} />
          <Route path="/similar-sites" element={<SimilarSites />} />
          <Route path="/similar-sites/:assetId" element={<SimilarSites />} />
          <Route path="/review" element={<Review />} />
          <Route path="/data" element={<Data />} />
          {/* Legacy routes preserved */}
          <Route path="/detect" element={<Detect />} />
          <Route path="/gis" element={<GIS />} />
        </Routes>
      </AnimatePresence>
    </div>
  )
}

export default App
