import { useNavigate } from 'react-router-dom'
import CategorySection, { type CategoryData } from '../components/tutorial/CategorySection'
import ExamplePrompt from '../components/tutorial/ExamplePrompt'

const CATEGORIES: CategoryData[] = [
  {
    id: 'memory',
    title: 'Memory & Personalization',
    description: 'Butler learns your preferences and adapts to you',
    icon: '\u{1F9E0}',
    tools: [
      {
        name: 'Remember Things',
        description: 'Store facts about your preferences, habits, and interests',
        examples: [
          'Remember that I prefer thriller movies',
          'I like my coffee black with no sugar',
          'My favourite football team is Arsenal',
        ],
      },
      {
        name: 'Recall Information',
        description: 'Ask Butler what it knows about you',
        examples: [
          'What do you know about my preferences?',
          'What are my favourite movies?',
        ],
      },
      {
        name: 'Adjust Personality',
        description: 'Change how Butler communicates with you',
        examples: [
          'Be more casual in your responses',
          'Use more humour',
          'Keep your answers short and concise',
        ],
      },
    ],
  },
  {
    id: 'weather',
    title: 'Weather',
    description: 'Current conditions and forecasts',
    icon: '\u{26C5}',
    tools: [
      {
        name: 'Weather Updates',
        description: 'Get current weather and multi-day forecasts for any location',
        examples: [
          "What's the weather like today?",
          'Will it rain tomorrow?',
          'Give me the 5-day forecast',
        ],
      },
    ],
  },
  {
    id: 'media',
    title: 'Movies, TV & Books',
    description: 'Search, request, and manage your media library',
    icon: '\u{1F3AC}',
    permission: 'media',
    tools: [
      {
        name: 'Movies',
        description: 'Search for movies and add them to your library',
        examples: [
          'Find the movie Inception',
          'Add The Batman to my library',
          'Is Oppenheimer in my collection?',
        ],
      },
      {
        name: 'TV Shows',
        description: 'Search for TV series and track episodes',
        examples: [
          'Add Breaking Bad to my shows',
          'Is The Last of Us downloading?',
          "What's the download progress?",
        ],
      },
      {
        name: 'Books & Audiobooks',
        description: 'Find and download books via Open Library',
        examples: [
          'Search for audiobooks by Stephen King',
          'Find the book Project Hail Mary',
          'Download Dune by Frank Herbert',
        ],
      },
      {
        name: 'Photos',
        description: 'Search your Immich photo library using natural language',
        examples: [
          'Show me photos from last Christmas',
          'Find pictures of the beach',
          'Search for photos of the dog',
        ],
      },
      {
        name: 'Playback',
        description: 'Control what\'s playing on Jellyfin across your devices',
        examples: [
          "What's currently playing?",
          'Pause the TV',
          'Show me recently added movies',
        ],
      },
      {
        name: 'File Management',
        description: 'Browse, move, copy, rename, and organise media files on the server',
        examples: [
          'List the files in Downloads',
          'Move that file to Media/Movies',
          'Create a folder for Season 2',
          'Find any low quality videos in my library',
        ],
      },
    ],
  },
  {
    id: 'home',
    title: 'Smart Home',
    description: 'Control lights, switches, and devices via Home Assistant',
    icon: '\u{1F3E0}',
    permission: 'home',
    tools: [
      {
        name: 'Device Control',
        description: 'Turn devices on/off, check states, and run automations',
        examples: [
          'Turn off the living room lights',
          'Set the bedroom temperature to 21',
          'Is the front door locked?',
          'What smart devices do I have?',
        ],
      },
    ],
  },
  {
    id: 'location',
    title: 'Location',
    description: 'Track household members via phone location',
    icon: '\u{1F4CD}',
    permission: 'location',
    tools: [
      {
        name: 'Phone Location',
        description: 'Check where household members are and if they\'re home',
        examples: [
          'Is everyone home?',
          'How far is Dad from home?',
          "Where's Mum?",
        ],
      },
    ],
  },
  {
    id: 'calendar',
    title: 'Calendar',
    description: 'View your Google Calendar events and schedule',
    icon: '\u{1F4C5}',
    permission: 'calendar',
    tools: [
      {
        name: 'Events',
        description: 'Check upcoming events and search your calendar',
        examples: [
          "What's on my calendar today?",
          'Any meetings tomorrow morning?',
          "What's my schedule this week?",
        ],
      },
    ],
  },
  {
    id: 'email',
    title: 'Email',
    description: 'Search and read your Gmail messages',
    icon: '\u{2709}\u{FE0F}',
    permission: 'email',
    tools: [
      {
        name: 'Gmail',
        description: 'Read recent emails, search by sender, subject, or content',
        examples: [
          'Check my recent emails',
          'Search for emails from Sarah',
          'Any emails about the project?',
        ],
      },
    ],
  },
  {
    id: 'automation',
    title: 'Reminders & Automation',
    description: 'Schedule recurring tasks and one-time reminders',
    icon: '\u{23F0}',
    permission: 'automation',
    tools: [
      {
        name: 'Scheduled Tasks',
        description: 'Create reminders, recurring checks, and automated routines',
        examples: [
          'Remind me to water plants every Monday',
          'Send me a weather update every morning',
          'What reminders do I have?',
        ],
      },
    ],
  },
  {
    id: 'communication',
    title: 'WhatsApp',
    description: 'Send messages via WhatsApp',
    icon: '\u{1F4AC}',
    permission: 'communication',
    tools: [
      {
        name: 'Messages',
        description: 'Send WhatsApp notifications to yourself or household members',
        examples: [
          "Send a WhatsApp to Mum saying I'm on my way",
          'Message the family group about dinner',
        ],
      },
    ],
  },
  {
    id: 'system',
    title: 'Server & System',
    description: 'Monitor server health, storage, and updates',
    icon: '\u{1F5A5}\u{FE0F}',
    tools: [
      {
        name: 'Health Checks',
        description: 'Check if all services are running and view active alerts',
        examples: [
          "How's the server doing?",
          'Are all services running?',
          'Any health alerts?',
        ],
      },
      {
        name: 'Storage',
        description: 'Monitor disk usage on the external drive and internal SSD',
        examples: [
          'Check storage usage',
          'How much space is left?',
          "What's using the most storage?",
        ],
      },
    ],
  },
]

const QUICK_START_PROMPTS = [
  "What's the weather like today?",
  "What's on my calendar?",
  'Find me a good movie to watch',
  "How's the server doing?",
]

export default function Tutorial() {
  const navigate = useNavigate()

  return (
    <div className="p-4 space-y-6 pb-24 md:pb-6">
      {/* Header */}
      <div>
        <h1 className="text-xl font-bold text-butler-100">What Butler Can Do</h1>
        <p className="text-sm text-butler-400 mt-1">
          Your AI assistant for media, smart home, and more. Try asking any of these.
        </p>
      </div>

      {/* Quick Start */}
      <div className="space-y-3">
        <h2 className="text-sm font-medium text-butler-400 uppercase tracking-wide">Quick Start</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {QUICK_START_PROMPTS.map((prompt) => (
            <ExamplePrompt key={prompt} prompt={prompt} />
          ))}
        </div>
      </div>

      {/* Categories */}
      <div className="space-y-3">
        <h2 className="text-sm font-medium text-butler-400 uppercase tracking-wide">All Features</h2>
        <div className="space-y-2">
          {CATEGORIES.map((category, i) => (
            <CategorySection
              key={category.id}
              category={category}
              defaultOpen={i === 0}
            />
          ))}
        </div>
      </div>

      {/* Settings CTA */}
      <div className="card p-4 border-accent/20 bg-accent/5">
        <div className="flex items-start gap-3">
          <svg className="w-5 h-5 text-accent shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <div className="flex-1">
            <p className="text-sm text-butler-200">
              Some features need permissions to be enabled. You can manage these in Settings.
            </p>
            <button
              onClick={() => navigate('/settings')}
              className="mt-2 text-sm font-medium text-accent hover:text-accent-light transition-colors"
            >
              Go to Settings &rarr;
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
