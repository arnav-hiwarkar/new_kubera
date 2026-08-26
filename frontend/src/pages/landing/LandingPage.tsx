import { useState } from 'react'
import { LandingHeader } from './components/LandingHeader'
import { LandingHero } from './components/LandingHero'
import { ProblemVsKubera } from './components/ProblemVsKubera'
import { ModuleShowcase } from './components/ModuleShowcase'
import { WhyItPaysOff } from './components/WhyItPaysOff'
import { PricingSection } from './components/PricingSection'
import { LandingFooter } from './components/LandingFooter'
import { LeadModal } from './components/LeadModal'

export function LandingPage() {
  const [modalOpen, setModalOpen] = useState(false)
  const [initialEmail, setInitialEmail] = useState('')

  const handleOpenModal = (email = '') => {
    setInitialEmail(email)
    setModalOpen(true)
  }

  return (
    <div className="min-h-screen bg-white text-slate-900 selection:bg-indigo-500 selection:text-white">
      <LandingHeader onRequestAccess={() => handleOpenModal()} />
      <main>
        <LandingHero onDirectSubmit={(email) => handleOpenModal(email)} />
        <ProblemVsKubera />
        <ModuleShowcase onRequestAccess={() => handleOpenModal()} />
        <WhyItPaysOff />
        <PricingSection onRequestAccess={() => handleOpenModal()} />
      </main>
      <LandingFooter onRequestAccess={() => handleOpenModal()} />
      <LeadModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        initialEmail={initialEmail}
      />
    </div>
  )
}
