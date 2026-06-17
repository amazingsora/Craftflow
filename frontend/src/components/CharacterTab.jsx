import { useState } from 'react'
import { apiFetch } from './characterTabShared.js'
import { ProjectsView, ProjectCreateView, CharacterListView, FactionView, CharacterCreateView } from './characterTabViews.jsx'
import { CharacterDetailView } from './CharacterDetailView.jsx'


// ── CharacterDetailView ───────────────────────────────────────────────────────


// ── Main ──────────────────────────────────────────────────────────────────────

export default function CharacterTab({ onAddHistory, onSendToGenerate, capability = { ipa_supported: true, cn_supported: true } }) {
  // view: 'projects' | 'project_create' | 'char_list' | 'faction_detail' | 'char_create' | 'char_detail'
  const [view, setView] = useState('projects')
  const [selectedProject, setSelectedProject] = useState(null)
  const [selectedChar, setSelectedChar] = useState(null)
  const [selectedFaction, setSelectedFaction] = useState(null)
  const [allChars, setAllChars] = useState([])       // all chars in current project (for FactionView add-member)
  const [allFactions, setAllFactions] = useState([]) // all factions in current project (for CharacterDetailView)
  const [projectsKey, setProjectsKey] = useState(0)
  const [charListKey, setCharListKey] = useState(0)
  const [autoEditProject, setAutoEditProject] = useState(false)
  const [returnTo, setReturnTo] = useState('char_list') // where to go back from char_detail

  const goProjects = () => { setView('projects'); setProjectsKey(k => k + 1); setAutoEditProject(false) }
  const goCharList = () => { setView('char_list'); setCharListKey(k => k + 1) }
  const goFactionDetail = () => setView('faction_detail')

  // Load project-level data when entering char_list or faction_detail
  const loadProjectData = async (projectId) => {
    const [chars, facts] = await Promise.all([
      apiFetch(`/projects/${projectId}/characters`).catch(() => []),
      apiFetch(`/projects/${projectId}/factions`).catch(() => []),
    ])
    setAllChars(chars)
    setAllFactions(facts)
  }

  if (view === 'project_create') {
    return (
      <ProjectCreateView
        onBack={goProjects}
        onCreate={(p) => { setSelectedProject(p); setView('char_list') }}
      />
    )
  }

  if (view === 'char_create' && selectedProject) {
    return (
      <CharacterCreateView
        project={selectedProject}
        onBack={goCharList}
        onCreate={(c) => { setSelectedChar(c); setReturnTo('char_list'); setView('char_detail') }}
      />
    )
  }

  if (view === 'char_detail' && selectedChar && selectedProject) {
    return (
      <CharacterDetailView
        character={selectedChar}
        project={selectedProject}
        allFactions={allFactions}
        onBack={() => returnTo === 'faction_detail' ? goFactionDetail() : goCharList()}
        onDeleted={goCharList}
        onAddHistory={onAddHistory}
        onSendToGenerate={onSendToGenerate}
        capability={capability}
      />
    )
  }

  if (view === 'faction_detail' && selectedFaction && selectedProject) {
    return (
      <FactionView
        faction={selectedFaction}
        project={selectedProject}
        allChars={allChars}
        onBack={goCharList}
        onSelectChar={(c) => { setSelectedChar(c); setReturnTo('faction_detail'); setView('char_detail') }}
      />
    )
  }

  if (view === 'char_list' && selectedProject) {
    return (
      <CharacterListView
        key={charListKey}
        project={selectedProject}
        autoEdit={autoEditProject}
        onBackToProjects={goProjects}
        onSelectChar={(c) => {
          loadProjectData(selectedProject.id)
          setSelectedChar(c); setReturnTo('char_list'); setView('char_detail')
        }}
        onCreateChar={() => setView('char_create')}
        onSelectFaction={(f) => {
          loadProjectData(selectedProject.id)
          setSelectedFaction(f); setView('faction_detail')
        }}
      />
    )
  }

  return (
    <ProjectsView
      key={projectsKey}
      onSelect={(p) => { setAutoEditProject(false); setSelectedProject(p); setView('char_list') }}
      onCreateClick={() => setView('project_create')}
      onEdit={(p) => { setAutoEditProject(true); setSelectedProject(p); setCharListKey(k => k + 1); setView('char_list') }}
    />
  )
}
