import { useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, useInView } from 'framer-motion'
import {
  Upload,
  Cpu,
  Download,
  Building2,
  TreePine,
  Droplets,
  Route,
  Trees,
  Waves,
  Car,
  Trash2,
  Sun,
  ChevronDown,
  ArrowRight,
  TrendingUp,
  Shield,
  Map,
} from 'lucide-react'
import Globe3D from '../components/Globe3D'
import AnimatedCounter from '../components/AnimatedCounter'
import { assetClasses, howItWorksSteps } from '../data/content'

const iconMap: Record<string, React.ComponentType<{ className?: string; style?: React.CSSProperties }>> = {
  upload: Upload,
  cpu: Cpu,
  download: Download,
  buildings: Building2,
  trees: TreePine,
  water: Droplets,
  roads: Route,
  parks: Trees,
  drains: Waves,
  vehicles: Car,
  waste: Trash2,
  solar: Sun,
}

const priorityColors: Record<string, string> = {
  'Must have': 'text-teal-600 bg-teal-50 border-teal-200',
  'Good to have': 'text-amber-700 bg-amber-50 border-amber-200',
  'Optional': 'text-stone-500 bg-stone-50 border-stone-200',
}

const stats = [
  { value: 68000, suffix: '+', label: 'km Railway Network' },
  { value: 9, label: 'Asset Classes' },
  { value: 2, prefix: '<', suffix: 's', label: 'Inference Time' },
  { value: 91, suffix: '%', label: 'Avg. Accuracy' },
]

export default function Landing() {
  const navigate = useNavigate()
  const howItWorksRef = useRef<HTMLDivElement>(null)
  const assetClassesRef = useRef<HTMLDivElement>(null)
  const timelineRef = useRef<HTMLDivElement>(null)

  const howItWorksInView = useInView(howItWorksRef, { once: true, margin: '-80px' })
  const assetClassesInView = useInView(assetClassesRef, { once: true, margin: '-80px' })
  const timelineInView = useInView(timelineRef, { once: true, margin: '-80px' })

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="bg-[#fafaf9]"
    >
      {/* ============ HERO ============ */}
      <section className="relative pt-24 pb-16 sm:pt-28 sm:pb-20 lg:pt-32 lg:pb-24 overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-b from-teal-50/40 via-transparent to-transparent pointer-events-none" />
        <div
          className="absolute inset-0 opacity-[0.04] pointer-events-none"
          style={{
            backgroundImage: 'radial-gradient(circle at 1px 1px, #0d9488 1px, transparent 0)',
            backgroundSize: '32px 32px',
          }}
        />

        <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid lg:grid-cols-2 gap-10 lg:gap-12 items-center">
            {/* Text */}
            <div className="flex flex-col gap-6 lg:gap-8 order-2 lg:order-1">
              <motion.div
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5 }}
                className="inline-flex items-center self-start gap-2 px-3 py-1.5 rounded-full bg-white border border-stone-200 shadow-soft"
              >
                <span className="w-1.5 h-1.5 rounded-full bg-teal-500" />
                <span className="text-xs font-medium text-stone-700 tracking-wide">
                  AI-Powered Asset Detection
                </span>
              </motion.div>

              <motion.h1
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6, delay: 0.1 }}
                className="font-['Space_Grotesk'] text-4xl sm:text-5xl lg:text-6xl xl:text-7xl font-bold text-stone-900 leading-[1.05] tracking-tight text-balance"
              >
                AI Eyes on Every{' '}
                <span className="text-teal-600">Railway Asset.</span>
                <br />
                In Real Time.
              </motion.h1>

              <motion.p
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6, delay: 0.2 }}
                className="text-base sm:text-lg text-stone-600 max-w-xl leading-relaxed text-pretty"
              >
                Harness deep learning to automatically detect, classify, and map spatial assets from satellite and drone imagery. Built for Indian Railways and DIGIT Urban Governance.
              </motion.p>

              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6, delay: 0.3 }}
                className="flex flex-col sm:flex-row gap-3"
              >
                <button
                  onClick={() => navigate('/detect')}
                  className="px-6 py-3.5 bg-teal-600 text-white rounded-xl font-semibold text-base
                           shadow-medium hover:bg-teal-700 hover:shadow-large active:scale-[0.98]
                           transition-all duration-200 inline-flex items-center justify-center gap-2"
                >
                  Start Detection
                  <ArrowRight className="w-4.5 h-4.5" />
                </button>

                <button
                  onClick={() => navigate('/gis')}
                  className="px-6 py-3.5 bg-white text-stone-800 rounded-xl font-semibold text-base
                           border border-stone-200 hover:border-stone-300 hover:bg-stone-50 active:scale-[0.98]
                           transition-all duration-200 inline-flex items-center justify-center gap-2"
                >
                  <Map className="w-4.5 h-4.5 text-teal-600" />
                  View GIS Map
                </button>
              </motion.div>

              {/* Stats */}
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6, delay: 0.4 }}
                className="grid grid-cols-2 sm:grid-cols-4 gap-x-4 gap-y-5 pt-6 mt-2 border-t border-stone-200"
              >
                {stats.map((stat, index) => (
                  <div key={index}>
                    <p className="font-['Space_Grotesk'] text-2xl sm:text-3xl font-bold text-stone-900 tracking-tight">
                      <AnimatedCounter value={stat.value} prefix={stat.prefix} suffix={stat.suffix} />
                    </p>
                    <p className="text-xs sm:text-sm text-stone-500 mt-1">{stat.label}</p>
                  </div>
                ))}
              </motion.div>
            </div>

            {/* Globe */}
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.8, delay: 0.2 }}
              className="order-1 lg:order-2 relative w-full aspect-square max-w-[460px] mx-auto lg:max-w-none lg:aspect-auto lg:h-[520px] xl:h-[580px]"
            >
              <Globe3D />
            </motion.div>
          </div>
        </div>

        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1, y: [0, 6, 0] }}
          transition={{
            opacity: { delay: 1.2, duration: 0.5 },
            y: { delay: 1.2, duration: 1.8, repeat: Infinity },
          }}
          className="hidden lg:flex absolute bottom-6 left-1/2 -translate-x-1/2 flex-col items-center gap-1.5 text-stone-400"
        >
          <span className="text-[10px] uppercase tracking-widest">Scroll</span>
          <ChevronDown className="w-4 h-4" />
        </motion.div>
      </section>

      {/* ============ HOW IT WORKS ============ */}
      <section ref={howItWorksRef} className="py-20 lg:py-28 bg-white border-y border-stone-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={howItWorksInView ? { opacity: 1, y: 0 } : {}}
            transition={{ duration: 0.6 }}
            className="text-center mb-12 lg:mb-16 flex flex-col items-center gap-4"
          >
            <span className="px-3 py-1 rounded-full bg-teal-50 text-teal-700 text-xs font-semibold tracking-wide uppercase">
              Process
            </span>
            <h2 className="font-['Space_Grotesk'] text-3xl sm:text-4xl lg:text-5xl font-bold text-stone-900 tracking-tight">
              How It Works
            </h2>
            <p className="text-stone-600 max-w-2xl text-base sm:text-lg">
              Three simple steps to transform satellite imagery into actionable asset data.
            </p>
          </motion.div>

          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5 lg:gap-6">
            {howItWorksSteps.map((step, index) => {
              const Icon = iconMap[step.icon] || Upload
              return (
                <motion.div
                  key={step.step}
                  initial={{ opacity: 0, y: 30 }}
                  animate={howItWorksInView ? { opacity: 1, y: 0 } : {}}
                  transition={{ delay: index * 0.12, duration: 0.5 }}
                  className="relative bg-white rounded-2xl p-6 lg:p-7 border border-stone-200 hover:border-teal-300 hover:shadow-medium transition-all duration-300 group"
                >
                  <div className="flex items-center justify-between mb-6">
                    <div className="w-12 h-12 rounded-xl bg-teal-50 flex items-center justify-center group-hover:bg-teal-100 transition-colors">
                      <Icon className="w-6 h-6 text-teal-600" />
                    </div>
                    <span className="font-['Space_Grotesk'] text-3xl font-bold text-stone-200">0{step.step}</span>
                  </div>
                  <h3 className="font-['Space_Grotesk'] text-xl font-semibold text-stone-900 mb-2">{step.title}</h3>
                  <p className="text-stone-600 text-sm leading-relaxed">{step.description}</p>
                </motion.div>
              )
            })}
          </div>
        </div>
      </section>

      {/* ============ ASSET CLASSES ============ */}
      <section ref={assetClassesRef} className="py-20 lg:py-28 bg-[#fafaf9]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={assetClassesInView ? { opacity: 1, y: 0 } : {}}
            transition={{ duration: 0.6 }}
            className="text-center mb-12 lg:mb-16 flex flex-col items-center gap-4"
          >
            <span className="px-3 py-1 rounded-full bg-teal-50 text-teal-700 text-xs font-semibold tracking-wide uppercase">
              Detection Capabilities
            </span>
            <h2 className="font-['Space_Grotesk'] text-3xl sm:text-4xl lg:text-5xl font-bold text-stone-900 tracking-tight">
              9 Asset Classes
            </h2>
            <p className="text-stone-600 max-w-2xl text-base sm:text-lg">
              Our AI model detects and classifies nine categories of spatial assets, from essential infrastructure to environmental features.
            </p>
            {/* Priority legend */}
            <div className="flex flex-wrap items-center justify-center gap-2 mt-1">
              {['Must have', 'Good to have', 'Optional'].map((p) => (
                <span key={p} className={`px-2.5 py-1 rounded-full text-xs font-medium border ${priorityColors[p]}`}>
                  {p}
                </span>
              ))}
            </div>
          </motion.div>

          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4 lg:gap-5">
            {assetClasses.map((asset, index) => {
              const Icon = iconMap[asset.icon] || Building2
              return (
                <motion.div
                  key={asset.id}
                  initial={{ opacity: 0, y: 20 }}
                  animate={assetClassesInView ? { opacity: 1, y: 0 } : {}}
                  transition={{ delay: index * 0.07, duration: 0.5 }}
                  whileHover={{ y: -3 }}
                  className="bg-white rounded-xl p-5 border border-stone-200 hover:shadow-medium transition-all duration-300"
                >
                  <div className="flex items-start gap-4">
                    <div
                      className="w-11 h-11 rounded-xl flex items-center justify-center shrink-0"
                      style={{ backgroundColor: `${asset.color}18` }}
                    >
                      <Icon className="w-5 h-5" style={{ color: asset.color }} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-start justify-between gap-2 mb-1">
                        <h3 className="font-['Space_Grotesk'] text-base font-semibold text-stone-900 leading-snug">
                          {asset.label}
                        </h3>
                        <span className={`shrink-0 px-2 py-0.5 rounded-full text-[10px] font-semibold border ${priorityColors[asset.priority]}`}>
                          {asset.priority === 'Must have' ? '★' : asset.priority === 'Good to have' ? '◆' : '○'}
                        </span>
                      </div>
                      <p className="text-xs text-stone-500 leading-relaxed">{asset.description}</p>
                    </div>
                  </div>
                </motion.div>
              )
            })}
          </div>
        </div>
      </section>

      {/* ============ BUILT FOR RAILWAYS ============ */}
      <section ref={timelineRef} className="py-20 lg:py-28 bg-white border-y border-stone-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={timelineInView ? { opacity: 1, y: 0 } : {}}
            transition={{ duration: 0.6 }}
            className="text-center mb-12 lg:mb-16 flex flex-col items-center gap-4"
          >
            <span className="px-3 py-1 rounded-full bg-amber-50 text-amber-800 text-xs font-semibold tracking-wide uppercase">
              Real-World Impact
            </span>
            <h2 className="font-['Space_Grotesk'] text-3xl sm:text-4xl lg:text-5xl font-bold text-stone-900 tracking-tight">
              Built for Indian Railways
            </h2>
            <p className="text-stone-600 max-w-2xl text-base sm:text-lg">
              Solving real problems in railway asset management and urban governance.
            </p>
          </motion.div>

          <div className="grid md:grid-cols-2 gap-5 lg:gap-6 max-w-5xl mx-auto">
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={timelineInView ? { opacity: 1, y: 0 } : {}}
              transition={{ delay: 0.1, duration: 0.5 }}
              className="bg-stone-50 rounded-2xl p-6 lg:p-7 border border-stone-200"
            >
              <div className="flex items-center gap-3 mb-5">
                <div className="w-10 h-10 rounded-lg bg-stone-200 flex items-center justify-center">
                  <TrendingUp className="w-5 h-5 text-stone-600" />
                </div>
                <h3 className="font-['Space_Grotesk'] text-xl font-semibold text-stone-900">The Challenge</h3>
              </div>
              <ul className="flex flex-col gap-3 text-stone-600 text-sm sm:text-base">
                {[
                  'Paper-based asset registers with no real-time visibility',
                  'Manual surveys take months and miss dynamic changes',
                  'Revenue loss from unmanaged land assets',
                ].map((text, i) => (
                  <li key={i} className="flex items-start gap-3">
                    <span className="w-1.5 h-1.5 rounded-full bg-stone-400 mt-2 shrink-0" />
                    <span className="leading-relaxed">{text}</span>
                  </li>
                ))}
              </ul>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={timelineInView ? { opacity: 1, y: 0 } : {}}
              transition={{ delay: 0.2, duration: 0.5 }}
              className="bg-teal-50/60 rounded-2xl p-6 lg:p-7 border border-teal-100"
            >
              <div className="flex items-center gap-3 mb-5">
                <div className="w-10 h-10 rounded-lg bg-teal-100 flex items-center justify-center">
                  <Shield className="w-5 h-5 text-teal-700" />
                </div>
                <h3 className="font-['Space_Grotesk'] text-xl font-semibold text-stone-900">The Solution</h3>
              </div>
              <ul className="flex flex-col gap-3 text-stone-700 text-sm sm:text-base">
                {[
                  'AI-powered detection from satellite and drone imagery',
                  'Real-time asset mapping across 9 spatial categories',
                  'Direct integration with DIGIT Asset Registry',
                ].map((text, i) => (
                  <li key={i} className="flex items-start gap-3">
                    <span className="w-1.5 h-1.5 rounded-full bg-teal-600 mt-2 shrink-0" />
                    <span className="leading-relaxed">{text}</span>
                  </li>
                ))}
              </ul>
            </motion.div>
          </div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={timelineInView ? { opacity: 1, y: 0 } : {}}
            transition={{ delay: 0.3, duration: 0.5 }}
            className="mt-12 lg:mt-16 grid grid-cols-1 sm:grid-cols-3 gap-4 sm:gap-6 max-w-4xl mx-auto"
          >
            {[
              { icon: TrendingUp, value: '10x', label: 'Faster Detection' },
              { icon: Shield, value: '9', label: 'Asset Categories' },
              { icon: Building2, value: 'Rs 100Cr+', label: 'Potential Savings' },
            ].map((item, index) => (
              <div key={index} className="text-center bg-stone-50 rounded-xl p-5 sm:p-6 border border-stone-200">
                <div className="w-12 h-12 rounded-xl bg-white shadow-soft flex items-center justify-center mx-auto mb-3">
                  <item.icon className="w-5 h-5 text-teal-600" />
                </div>
                <p className="font-['Space_Grotesk'] text-2xl sm:text-3xl font-bold text-stone-900">{item.value}</p>
                <p className="text-stone-500 text-xs sm:text-sm mt-1">{item.label}</p>
              </div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* ============ CTA ============ */}
      <section className="py-20 lg:py-24 bg-[#fafaf9]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6 }}
            className="relative overflow-hidden rounded-3xl bg-stone-900 p-8 sm:p-12 lg:p-16 text-center"
          >
            <div
              className="absolute inset-0 opacity-[0.06] pointer-events-none"
              style={{
                backgroundImage: 'radial-gradient(circle at 2px 2px, white 1px, transparent 0)',
                backgroundSize: '28px 28px',
              }}
            />
            <div className="absolute -top-24 -right-24 w-72 h-72 rounded-full bg-teal-500/20 blur-3xl pointer-events-none" />
            <div className="relative flex flex-col items-center gap-6">
              <h2 className="font-['Space_Grotesk'] text-3xl sm:text-4xl lg:text-5xl font-bold text-white tracking-tight max-w-3xl text-balance">
                Ready to Transform Asset Management?
              </h2>
              <p className="text-stone-300 max-w-xl text-base sm:text-lg">
                Start detecting and classifying spatial assets from your satellite imagery today.
              </p>
              <div className="flex flex-col sm:flex-row gap-3 mt-2">
                <button
                  onClick={() => navigate('/detect')}
                  className="px-7 py-3.5 bg-white text-stone-900 rounded-xl font-semibold text-base
                           hover:bg-stone-100 active:scale-[0.98] transition-all duration-200
                           inline-flex items-center gap-2 shadow-large"
                >
                  Start Detection Now
                  <ArrowRight className="w-4.5 h-4.5" />
                </button>
                <button
                  onClick={() => navigate('/gis')}
                  className="px-7 py-3.5 bg-white/10 text-white border border-white/20 rounded-xl font-semibold text-base
                           hover:bg-white/20 active:scale-[0.98] transition-all duration-200
                           inline-flex items-center gap-2"
                >
                  <Map className="w-4.5 h-4.5" />
                  Explore GIS
                </button>
              </div>
            </div>
          </motion.div>
        </div>
      </section>

      {/* ============ FOOTER ============ */}
      <footer className="py-8 border-t border-stone-200 bg-white">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex flex-col sm:flex-row items-center justify-between gap-3">
            <p className="text-stone-500 text-sm">© 2026 AerialEye. Built for Indian Railways Hackathon.</p>
            <div className="flex items-center gap-2 text-sm">
              <span className="text-stone-500">Powered by</span>
              <span className="text-amber-700 font-semibold">DIGIT</span>
              <span className="text-stone-300">×</span>
              <span className="text-teal-700 font-semibold">eGov Foundation</span>
            </div>
          </div>
        </div>
      </footer>
    </motion.div>
  )
}
