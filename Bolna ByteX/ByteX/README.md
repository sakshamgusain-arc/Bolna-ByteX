# ByteX AI — Frontend Client

The frontend client for **ByteX AI**, built with **React 19**, **TypeScript**, **Vite 8**, and **Three.js**. It features an interactive, state-reactive 3D WebGL orb, real-time voice streaming with sub-second speech endpointing and acoustic barge-in, unified command routing, and a clean futuristic UI.

---

## 🚀 Key Features

- **Dynamic 3D WebGL Orb (`ByteXOrb`)**:
  - Interactive WebGL/Canvas visualizer powered by Three.js, OGL, and shaders.
  - Reactive visual states: `idle`, `listening`, `thinking`, `speaking`, `executing`, `processing`, `success`, and `error`.
  - Customizable orb visuals via `OrbCustomizer` (colors, glow intensity, speed, amplitude, and resonator).
- **Strict ₹0 Real-Time Voice Pipeline**:
  - **Speech-to-Text (STT)**: Native Web Speech API (`SpeechRecognition` / `webkitSpeechRecognition`) with client-side dynamic noise gate.
  - **Acoustic Barge-In (`bargeInService.ts`)**: Detects incoming user voice during TTS playback to instantly cancel synthesis and resume listening.
  - **Conversational Endpointing**: Debounced trailing silence windows for fluid conversational turn-taking.
  - **Neural Text-to-Speech (TTS)**: Web SpeechSynthesis targeting Microsoft Online Natural neural voices with local SAPI5 fallback.
- **Real-Time WebSocket Protocol**:
  - Bidirectional communication on `ws://127.0.0.1:8000/ws`.
  - Real-time token streaming (`ASSISTANT_DELTA`), state events, and live system monitoring events.
- **Desktop & Phone Companion**:
  - Edge CDP remote control integration on port `9222`.
  - QR Code and token-based pairing with Android companion app (`phonePairingService.ts`).
- **Comprehensive UI Controls**:
  - Chat history with markdown rendering and code syntax highlighting.
  - Quick action shortcuts, state docks, search docks, and audio setting controls.

---

## 📦 Tech Stack

- **Framework**: React 19 (`react`, `react-dom`)
- **Language**: TypeScript 6
- **Build Tool**: Vite 8 with HMR
- **3D Graphics & Animations**: Three.js, OGL, `thinking-orbs`, `motion`
- **Icons & Styling**: Lucide React, modern responsive CSS3 variables
- **Linter**: Oxlint

---

## 🛠️ Getting Started

### Prerequisites

- **Node.js**: v18.0.0 or higher
- **npm** or **pnpm** / **yarn**

### 1. Install Dependencies

```bash
npm install
```

### 2. Environment Configuration

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Default variables:
```ini
VITE_API_URL=http://127.0.0.1:8000/api
VITE_WS_URL=ws://127.0.0.1:8000/ws
```

### 3. Development Server

Start Vite in dev mode:

```bash
npm run dev
```

The frontend will be available at `http://localhost:5173`.

### 4. Build for Production

```bash
npm run build
```

Preview the production build:
```bash
npm run preview
```

### 5. Linting

```bash
npm run lint
```

---

## 📁 Source Directory Structure

```
src/
├── assets/                 # Static assets, hero images, and SVGs
├── components/
│   ├── ByteXOrb/           # 3D WebGL Orb component, shaders, and styling
│   ├── Chat/               # ChatHistory and ChatMessage components
│   ├── CommandInput/       # Voice & text command input with shortcuts
│   ├── Header/             # Top bar with status and navigation
│   ├── Notifications/      # Toast and confirmation banners
│   ├── OrbCustomizer/      # Visual parameter controls for the 3D Orb
│   ├── OrbStateSelector/   # Manual state inspection dock
│   ├── QuickActions/       # Predefined action buttons
│   ├── SearchDock/         # Desktop and web search dock
│   ├── Settings/           # Audio, AI model, and permission settings
│   ├── StateDock/          # System state indicators
│   ├── StatusIndicator/    # Connection and backend health pill
│   ├── Suggestions/        # Proactive suggestion cards
│   └── ui/                 # Reusable UI primitives (LightRays, buttons, etc.)
├── hooks/
│   ├── useCommand.ts       # Central command dispatch hook
│   ├── useKeyboardShortcuts.ts # Global hotkey listeners
│   └── useVoice.ts         # Voice recognition & continuous listening hook
├── lib/
│   └── utils.ts            # Utility functions
├── pages/
│   └── Home/               # Main application container
├── services/
│   ├── bargeInService.ts   # Real-time Web Audio API voice barge-in detector
│   ├── bytexApi.ts         # REST API client for backend
│   ├── mockAssistant.ts    # Offline development mock provider
│   ├── orbCustomizerService.ts # LocalStorage-backed orb customization
│   ├── phonePairingService.ts # QR and token phone pairing manager
│   ├── sttService.ts       # SpeechRecognition lifecycle and debounce
│   ├── ttsService.ts       # Streaming sentence tokenizer & neural TTS engine
│   ├── voiceSettingsService.ts # Voice rate, pitch, and voice profile store
│   ├── wakeWordService.ts  # Wake-word detection and hands-free turn taking
│   └── __tests__/          # Vitest / Node test suites for audio pipeline
└── types/
    ├── index.ts            # Core API and messaging TypeScript types
    └── orb.ts              # Orb states and color configuration types
```
