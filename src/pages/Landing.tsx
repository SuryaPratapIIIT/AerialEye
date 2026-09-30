import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  Search,
  Activity,
  CheckSquare,
  ArrowRight,
  Database,
  Layers,
  Cpu,
} from 'lucide-react'

export default function Landing() {
  const navigate = useNavigate()

  return (
    <div className="relative min-h-screen bg-[#020617] overflow-hidden flex flex-col items-center justify-center">
      {/* Background Effects */}
      <div className="absolute inset-0 z-0">
        <div className="absolute top-1/4 left-1/4 w-[500px] h-[500px] bg-cyan-600/20 rounded-full blur-[120px] pointer-events-none mix-blend-screen" />
        <div className="absolute bottom-1/4 right-1/4 w-[600px] h-[600px] bg-blue-600/10 rounded-full blur-[150px] pointer-events-none mix-blend-screen" />
        
        {/* Grid pattern */}
        <div 
          className="absolute inset-0 opacity-[0.03]"
          style={{
            backgroundImage: `linear-gradient(rgba(255,255,255,1) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,1) 1px, transparent 1px)`,
            backgroundSize: '40px 40px'
          }}
        />
      </div>

      <div className="relative z-10 container-app pt-32 pb-20 flex flex-col items-center text-center">
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, ease: "easeOut" }}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-full border border-cyan-500/30 bg-cyan-500/10 backdrop-blur-md mb-8"
        >
          <span className="relative flex h-2.5 w-2.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-cyan-500"></span>
          </span>
          <span className="text-xs font-mono text-cyan-400 tracking-wider uppercase">System Online • v2.0 Platform</span>
        </motion.div>

        <motion.h1
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.1, ease: "easeOut" }}
          className="font-display text-5xl md:text-7xl lg:text-8xl font-bold tracking-tight text-white mb-6"
        >
          Intelligence from <br/>
          <span className="text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-blue-600 glow-text">Every Pixel.</span>
        </motion.h1>

        <motion.p
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.2, ease: "easeOut" }}
          className="text-lg md:text-xl text-slate-400 max-w-2xl mb-12"
        >
          A state-of-the-art spatial analysis platform. Discover scenes through semantic search, compute temporal changes instantly, and verify intelligence with absolute provenance.
        </motion.p>

        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.5, delay: 0.4 }}
          className="flex flex-col sm:flex-row gap-4"
        >
          <button
            onClick={() => navigate('/search')}
            className="group relative px-8 py-4 bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold rounded-xl overflow-hidden transition-all shadow-[0_0_20px_rgba(6,182,212,0.4)] hover:shadow-[0_0_30px_rgba(6,182,212,0.6)] flex items-center justify-center gap-2"
          >
            <div className="absolute inset-0 bg-white/20 translate-y-full group-hover:translate-y-0 transition-transform duration-300 ease-out" />
            <Search className="w-5 h-5 relative z-10" />
            <span className="relative z-10">Start Discovery</span>
          </button>

          <button
            onClick={() => navigate('/data')}
            className="px-8 py-4 bg-slate-800/50 hover:bg-slate-800 text-slate-200 border border-slate-700 hover:border-slate-500 font-semibold rounded-xl backdrop-blur-sm transition-all flex items-center justify-center gap-2"
          >
            <Database className="w-5 h-5 text-slate-400" />
            Manage Datasets
          </button>
        </motion.div>

        {/* Feature Cards */}
        <div className="grid md:grid-cols-3 gap-6 mt-24 w-full max-w-5xl">
           {[
             { title: "Semantic Retrieval", desc: "Query spatial data using natural language powered by CLIP.", icon: Search, color: "text-cyan-400", bg: "bg-cyan-500/10" },
             { title: "Temporal Analysis", desc: "Align and detect pixel-perfect heuristic changes over time.", icon: Activity, color: "text-blue-400", bg: "bg-blue-500/10" },
             { title: "Analyst Verification", desc: "Human-in-the-loop review queue for actionable intelligence.", icon: CheckSquare, color: "text-emerald-400", bg: "bg-emerald-500/10" }
           ].map((feat, i) => (
             <motion.div 
               key={feat.title}
               initial={{ opacity: 0, y: 20 }}
               animate={{ opacity: 1, y: 0 }}
               transition={{ duration: 0.5, delay: 0.6 + (i * 0.1) }}
               className="glass-panel p-6 rounded-2xl text-left glass-panel-hover flex flex-col gap-4"
             >
                <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${feat.bg} border border-slate-700/50`}>
                   <feat.icon className={`w-6 h-6 ${feat.color}`} />
                </div>
                <div>
                   <h3 className="text-lg font-display font-semibold text-slate-200 mb-2">{feat.title}</h3>
                   <p className="text-sm text-slate-400 leading-relaxed">{feat.desc}</p>
                </div>
             </motion.div>
           ))}
        </div>
      </div>
    </div>
  )
}
