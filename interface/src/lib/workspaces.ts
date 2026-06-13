import {
  AlertTriangle,
  BarChart3,
  Database,
  FlaskConical,
  LayoutDashboard,
  MonitorCog,
  ScrollText,
  ShieldCheck,
  TrendingUp,
  WalletCards,
  type LucideIcon,
} from 'lucide-react'

export type WorkspaceKey = 'trade' | 'review' | 'operate' | 'system'

export type WorkspaceTab = {
  slug: string
  label: string
  to: string
}

export type WorkspaceDefinition = {
  key: WorkspaceKey
  label: string
  to: string
  icon: LucideIcon
  description: string
  tabs: WorkspaceTab[]
}

export const workspaceDefinitions: WorkspaceDefinition[] = [
  {
    key: 'trade',
    label: 'Trade',
    to: '/trade',
    icon: LayoutDashboard,
    description: 'Live operator views for market analysis, scans, trades, and portfolio posture.',
    tabs: [
      { slug: 'overview', label: 'Overview', to: '/trade/overview' },
      { slug: 'markets', label: 'Markets', to: '/trade/markets' },
      { slug: 'scans', label: 'Scans', to: '/trade/scans' },
      { slug: 'trades', label: 'Trades', to: '/trade/trades' },
      { slug: 'portfolio', label: 'Portfolio', to: '/trade/portfolio' },
    ],
  },
  {
    key: 'review',
    label: 'Review',
    to: '/review',
    icon: TrendingUp,
    description: 'Historical audits, engine review, failure analysis, and learning evaluation.',
    tabs: [
      { slug: 'engine-performance', label: 'Engine Performance', to: '/review/engine/performance' },
      { slug: 'engine-behavior', label: 'Engine Behavior', to: '/review/engine/behavior' },
      { slug: 'failures', label: 'Failures', to: '/review/failures' },
      { slug: 'learning', label: 'Learning', to: '/review/learning' },
    ],
  },
  {
    key: 'operate',
    label: 'Operate',
    to: '/operate',
    icon: ShieldCheck,
    description: 'Runtime control surfaces, alerts, health, and operational diagnostics.',
    tabs: [
      { slug: 'control', label: 'Control', to: '/operate/control' },
      { slug: 'alerts', label: 'Alerts', to: '/operate/alerts' },
      { slug: 'logs', label: 'Logs', to: '/operate/logs' },
      { slug: 'config', label: 'Config', to: '/operate/config' },
    ],
  },
  {
    key: 'system',
    label: 'System',
    to: '/system',
    icon: MonitorCog,
    description: 'Preferences, storage, and low-frequency simulation surfaces.',
    tabs: [
      { slug: 'preferences', label: 'Preferences', to: '/system/preferences' },
      { slug: 'storage', label: 'Storage', to: '/system/storage' },
      { slug: 'simulations', label: 'Simulations', to: '/system/simulations' },
    ],
  },
]

export const workspaceByKey = Object.fromEntries(workspaceDefinitions.map((workspace) => [workspace.key, workspace])) as Record<WorkspaceKey, WorkspaceDefinition>

export const legacyRouteRedirects: Record<string, string> = {
  '/dashboard': '/trade/overview',
  '/markets': '/trade/markets',
  '/scans': '/trade/scans',
  '/trades': '/trade/trades',
  '/portfolio': '/trade/portfolio',
  '/failures': '/review/failures',
  '/analytics': '/review/engine/performance',
  '/learning': '/review/learning',
  '/performance': '/review/engine/behavior',
  '/admin': '/operate/control',
  '/alerts': '/operate/alerts',
  '/logs': '/operate/logs',
  '/settings': '/system/preferences',
  '/storage': '/system/storage',
  '/simulations': '/system/simulations',
  '/trading/dashboard': '/trade/overview',
  '/trading/markets': '/trade/markets',
  '/trading/scans': '/trade/scans',
  '/trading/trades': '/trade/trades',
  '/trading/portfolio': '/trade/portfolio',
  '/intelligence/failures': '/review/failures',
  '/intelligence/analytics': '/review/engine/performance',
  '/intelligence/learning': '/review/learning',
  '/intelligence/performance': '/review/engine/behavior',
  '/operations/admin': '/operate/control',
  '/operations/alerts': '/operate/alerts',
  '/operations/logs': '/operate/logs',
  '/operations/settings': '/operate/config',
  '/data/storage': '/system/storage',
  '/lab/simulations': '/system/simulations',
}

export const workspaceShortcuts = [
  { to: '/trade/overview', label: 'Overview', icon: LayoutDashboard },
  { to: '/trade/markets', label: 'Markets', icon: BarChart3 },
  { to: '/trade/trades', label: 'Trades', icon: ScrollText },
  { to: '/trade/portfolio', label: 'Portfolio', icon: WalletCards },
  { to: '/review/failures', label: 'Failures', icon: AlertTriangle },
  { to: '/review/engine/performance', label: 'Engine Performance', icon: TrendingUp },
  { to: '/review/learning', label: 'Learning', icon: TrendingUp },
  { to: '/operate/control', label: 'Control', icon: ShieldCheck },
  { to: '/system/storage', label: 'Storage', icon: Database },
  { to: '/system/simulations', label: 'Simulations', icon: FlaskConical },
] as const
