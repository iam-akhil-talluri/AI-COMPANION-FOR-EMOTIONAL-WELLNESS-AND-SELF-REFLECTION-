// IT 7993 CAPSTONE - FALL 2026
//Title: AI COMPANION FOR EMOTIONAL WELLNESS & SELF-REFLECTION
//Project Sponsor: Capgemini America, Inc.
//Instructor: Dr. Ying Xie
//Team P05-01: Shaheed Campbell, Cynthia Lakshminarayanan, Emmanuel Kofi Mensah, Korey Owens, Akhil Sai Talluri


/*
============================================================
BACKEND / AI INTEGRATION MAP
============================================================

Requests go to the FastAPI backend through src/services/.
The backend is the security boundary: it checks the signed-in user,
the admin role and session ownership on every request.
Full details: backend/docs/frontend-integration.md

1. AUTHENTICATION (services/authService.js)            CONNECTED
   POST /api/auth/login, POST /api/auth/register, GET /api/auth/me,
   POST /api/auth/logout. Pseudonymous accounts: username + password only.
   "Sign in as Administrator" sends admin: true; the server answers 403
   if the account is not an administrator.

2. CONVERSATIONS (services/chatService.js)              CONNECTED
   POST /api/sessions and POST /api/sessions/{session_id}/messages.

3. SAFETY / MODERATION                                  CONNECTED
   Runs inside the backend before any AI call (rules + OpenAI Moderation).
   The reply's status drives the screens:
     ok      show the reply
     support show the reply with support resources under it
     crisis  show the reviewed crisis message, then the Support & Crisis
             Resources screen (the AI is never called for these)
   If the check cannot run, the backend fails closed with 503
   safety_unavailable and the Safety Check Unavailable screen opens.

4. CONVERSATIONAL AI                                    CONNECTED
   OpenAI, called by the backend only after the safety check. Every AI reply
   is checked again before it is shown. The browser never sees the API key.

5. CONVERSATION HISTORY (services/chatService.js)       CONNECTED
   GET /api/sessions, GET /api/sessions/{session_id},
   DELETE /api/sessions/{session_id}. Only the signed-in user's sessions.

6. MESSAGE PERSISTENCE                                  CONNECTED
   MySQL stores sessions and messages (deleted after the retention period).

7. ANALYTICS / OPERATIONAL LOGGING (services/adminService.js)
   Admin statistics, safety, escalations, AI cost:
     GET /api/admin/analytics                          CONNECTED
   Admin "Recent Log Events": GET /api/admin/logs      CONNECTED
   Admin "Architecture Health": GET /api/health        CONNECTED
   My Insights and admin Coping Tool Activity          SAMPLE DATA (no endpoint yet)

8. COPING TOOLS
   Static, reviewed frontend content; no AI. Journal entries and tool
   counts are not stored yet (no backend endpoint).

============================================================
*/


import { useState, useEffect, useRef } from 'react'
import './App.css'
import { onUnauthorized } from './services/apiClient'
import { register, restoreSession, signIn, signOut } from './services/authService'
import {
  MAX_MESSAGE_LENGTH,
  createSession,
  deleteSession,
  getSession,
  listSessions,
  sendMessageToBackend
} from './services/chatService'
import {
  formatLogTime,
  formatNumber,
  formatUsd,
  getAdminAnalytics,
  getHealth,
  getRecentLogs
} from './services/adminService'

const CONVERSATION_STARTER = 'What would you like to talk about today?'

// Screens that send messages; the support and safety-error screens return to them.
const CHAT_SCREENS = ['conversation', 'reflection-chat', 'continue-session']

// One message bubble. role: user | assistant | notice (a system message, e.g. "no reply available").
// item.resources: reviewed support resources sent by the backend with a `support` or `crisis` reply.
function MessageBubble({ item }) {
  const className =
    item.role === 'user'
      ? 'message user-message'
      : item.role === 'notice'
        ? 'message assistant-message notice-message'
        : 'message assistant-message'

  const label =
    item.role === 'user' ? 'You' : item.role === 'notice' ? 'Notice' : 'AI Companion'

  return (
    <div className={className}>
      <span className='message-label'>{label}</span>
      <p>{item.text}</p>

      {item.resources?.length > 0 && (
        <div className='message-resources'>
          <strong>Support is available</strong>
          {item.resources.map((resource) => (
            <div className='message-resource' key={resource.id}>
              <div>
                <span className='message-resource-name'>{resource.name}</span>
                <span className='message-resource-description'>{resource.description}</span>
              </div>
              <a className='support-resource-button' href={resource.href}>{resource.action_label}</a>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

//MY ANALYTICS: Prototype Sample Data
//BACKEND INTEGRATION: no endpoint yet (GET /api/analytics/me is planned, owner: Korey)
const SAMPLE_ANALYTICS = {
  totalSessions: 12,
  sessionsThisWeek: 4,
  sessionsThisMonth: 9,
  lastVisit: 'Yesterday',
  typicalSessionMinutes: 9,
  //Sessions by day of the week, all time. These add up to totalSessions.
  weekdays: [
    { day: 'Mon', count: 2 },
    { day: 'Tue', count: 3 },
    { day: 'Wed', count: 1 },
    { day: 'Thu', count: 3 },
    { day: 'Fri', count: 1 },
    { day: 'Sat', count: 1 },
    { day: 'Sun', count: 1 },
  ],

  tools: [
    { name: 'Mindful Breathing', completed: 5 },
    { name: 'Journaling', completed: 3 },
    { name: 'Grounding', completed: 2 }
  ]
}

// ADMIN DASHBOARD DATA
// Statistics, safety decisions, escalations and AI cost come from GET /api/admin/analytics,
// Recent Log Events from GET /api/admin/logs, and Architecture Health from GET /api/health.
// The backend verifies the admin role and never returns message text or usernames.
// These zeros are shown until the first load finishes.
const EMPTY_ADMIN_ANALYTICS = {
  activeUsers: 0,
  totalSessions: 0,
  sessionsPerUser: 0,
  messagesSafetyChecked: 0,
  safetyCheckErrors: 0,
  sentToAIUnchecked: 0,
  weekdays: [],
  escalations: 0,
  crisisEscalations: 0,
  supportEscalations: 0,
  safetyDecisions: { clear: 0, concern: 0, error: 0 },
  boundaryReplies: 0,
  repliesBlocked: 0,
  aiUsage: {
    model: '',
    configured: false,
    requests: 0,
    inputTokens: 0,
    outputTokens: 0,
    totalTokens: 0,
    estimatedCost: 0,
    avgCostPerRequest: 0,
    avgLatencyMs: 0,
    repliesWithoutAI: 0,
    monthToDateCost: 0,
    monthlyBudget: null,
    budgetUtilization: null,
    byModel: [],
    daily: []
  }
}

// Coping Tool Activity: sample data (no backend endpoint for coping-tool usage yet).
const SAMPLE_COPING_TOOLS = [
  { name: 'Mindful Breathing', completed: 48 },
  { name: 'Grounding Exercise', completed: 31 },
  { name: 'Reflection Prompt', completed: 26 },
  { name: 'Journaling', completed: 19 }
]


function App() {
  // 'loading' while a saved sign-in is checked with the backend
  const [currentScreen, setCurrentScreen] = useState('loading')
  const [adminLogin, setAdminLogin] = useState(false)
  const [loginError, setLoginError] = useState('')
  const [userRole, setUserRole] = useState(null)
  const [currentUser, setCurrentUser] = useState(null)
  // 'signin' or 'register' (create a pseudonymous account)
  const [authMode, setAuthMode] = useState('signin')
  const [authBusy, setAuthBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [messages, setMessages] = useState([])
  const [activeConversationId, setActiveConversationId] = useState(null)
  const [reflectionMessage, setReflectionMessage] = useState('')
  const [reflectionMessages, setReflectionMessages] = useState([])
  const [reflectionSafetyChecking, setReflectionSafetyChecking] = useState(false)
  // The open reflection or continued session (from the backend: id, type, title, prompt, ...)
  const [selectedSession, setSelectedSession] = useState(null)
  // Shows the "Checking your message" state while the backend request runs.
  const [safetyChecking, setSafetyChecking] = useState(false)
  const [continueMessage, setContinueMessage] = useState('')
  const [continueMessages, setContinueMessages] = useState([])
  const [previousScreen, setPreviousScreen] = useState('home')
  // Where the Support & Crisis Resources and Safety Check Unavailable screens go back to.
  const [returnScreen, setReturnScreen] = useState('home')
  const [continueSafetyChecking, setContinueSafetyChecking] = useState(false)
  const [conversationStarter, setConversationStarter] = useState(CONVERSATION_STARTER)
  // Error shown on a screen when an action could not start (e.g. network down).
  const [screenNotice, setScreenNotice] = useState('')

  const reflectionPrompts = [
    'What has been on your mind most today?',
    'What has felt difficult recently?',
    'What is one thing that went better than you expected?',
    'What would you like to understand more clearly about how you are feeling?',
    'What has been taking up most of your energy lately?',
    'Is there something you have been putting off that you would like to think through?',
    'What is something you would like to make a little more space for today?',
    'What is one thing you wish you could pause and give yourself time to consider?'
  ]
  const [reflectionPrompt, setReflectionPrompt] = useState(reflectionPrompts[0])
  const [startingReflection, setStartingReflection] = useState(false)
  const [breathingActive, setBreathingActive] = useState(false)
  const [breathingPhase, setBreathingPhase] = useState('Inhale')
  const [breathingCount, setBreathingCount] = useState(4)
  const countRef = useRef(4)
  // End of the open chat's message list, so a new reply scrolls into view.
  const messageEndRef = useRef(null)

  // Data loaded from the backend for the History screen and the Admin Dashboard.
  const [conversationSessions, setConversationSessions] = useState([])
  const [recentLogs, setRecentLogs] = useState([])
  const [healthServices, setHealthServices] = useState([])
  const [adminAnalyticsData, setAdminAnalyticsData] = useState(null)
  // Which data screen finished loading last, and its error message if it failed.
  const [loadedScreen, setLoadedScreen] = useState({ screen: null, error: '' })
  const [openingSessionId, setOpeningSessionId] = useState(null)
  const [deletingSessionId, setDeletingSessionId] = useState(null)
  const [historyError, setHistoryError] = useState('')
  const screenLoading = ['history', 'admin'].includes(currentScreen) && loadedScreen.screen !== currentScreen
  const screenLoadError = loadedScreen.screen === currentScreen ? loadedScreen.error : ''

  // COPING TOOL USAGE
  // Counted in this browser tab only: the backend has no coping-usage endpoint yet.
  const [copingUsage, setCopingUsage] = useState({
    journaling: 0,
    grounding: 0,
    breathing: 0
  })

  function resetUserState() {
    setMessages([])
    setMessage('')
    setActiveConversationId(null)
    setReflectionMessages([])
    setReflectionMessage('')
    setContinueMessages([])
    setContinueMessage('')
    setSelectedSession(null)
    setConversationSessions([])
    setRecentLogs([])
    setHealthServices([])
    setAdminAnalyticsData(null)
    setReturnScreen('home')
    setLoadedScreen({ screen: null, error: '' })
    setScreenNotice('')
    setHistoryError('')
    setUserRole(null)
    setCurrentUser(null)
    setAdminLogin(false)
    setBreathingActive(false)
    setCopingUsage({ journaling: 0, grounding: 0, breathing: 0 })
  }

  // SIGN-IN RESTORE AND EXPIRY
  // A saved sign-in is checked with GET /api/auth/me. When any request answers
  // 401 (expired or signed out elsewhere), the user returns to the login screen.
  useEffect(() => {
    onUnauthorized((detail) => {
      resetUserState()
      setAuthMode('signin')
      setLoginError(detail || 'Please sign in again.')
      setCurrentScreen('login')
    })

    let cancelled = false
    restoreSession().then((user) => {
      if (cancelled) return
      if (user) {
        setCurrentUser(user)
        setUserRole(user.role)
        setCurrentScreen('home')
      } else {
        setCurrentScreen('login')
      }
    })

    return () => {
      cancelled = true
      onUnauthorized(null)
    }
  }, [])

  // Every screen opens at the top (e.g. the crisis resources screen after a long chat).
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [currentScreen])

  // Keep the newest message (and the "checking" bubble) visible in the open chat.
  useEffect(() => {
    messageEndRef.current?.scrollIntoView({ block: 'nearest' })
  }, [messages, reflectionMessages, continueMessages, safetyChecking, reflectionSafetyChecking,
    continueSafetyChecking])

  // SCREEN DATA
  // History and the Admin Dashboard load fresh data each time they open.
  useEffect(() => {
    const loaders = {
      history: async () => setConversationSessions(await listSessions()),
      admin: async () => {
        const [logs, health, analytics] = await Promise.all([
          getRecentLogs(10),
          getHealth(),
          getAdminAnalytics(7)
        ])
        setRecentLogs(logs)
        setHealthServices(health.services)
        setAdminAnalyticsData(analytics)
      }
    }

    const load = loaders[currentScreen]
    if (!load) return

    let cancelled = false
    load()
      .then(() => {
        if (!cancelled) setLoadedScreen({ screen: currentScreen, error: '' })
      })
      .catch((error) => {
        if (cancelled) return
        // Don't leave data from an earlier load on screen under the error.
        if (currentScreen === 'history') {
          setConversationSessions([])
        } else {
          setRecentLogs([])
          setHealthServices([])
          setAdminAnalyticsData(null)
        }
        setLoadedScreen({ screen: currentScreen, error: error.message })
      })

    return () => {
      cancelled = true
    }
  }, [currentScreen])


  useEffect(() => {
    if (!breathingActive) return
    countRef.current = 4
    const timer = setInterval(() => {

      if (countRef.current > 1) {
        countRef.current = countRef.current - 1
        setBreathingCount(countRef.current)
        return
      }
      setBreathingPhase((currentPhase) => {
        if (currentPhase === 'Inhale') {
          return 'Hold Full'
        }
        if (currentPhase === 'Hold Full') {
          return 'Exhale'
        }
        if (currentPhase === 'Exhale') {
          return 'Hold Empty'
        }
        return 'Inhale'
      })
      countRef.current = 4
      setBreathingCount(4)

    }, 1000)
    return () => clearInterval(timer)
  }, [breathingActive])
  const [journalText, setJournalText] = useState('')
  const [journalSaved, setJournalSaved] = useState(false)
  const [groundingStarted, setGroundingStarted] = useState(false)

  function recordCopingUsage(tool) {
    setCopingUsage((currentUsage) => ({
      ...currentUsage,
      [tool]: currentUsage[tool] + 1
    }))
  }

  // AUTHENTICATION
  async function handleAuthSubmit(event) {
    event.preventDefault()
    if (authBusy) return

    const form = event.currentTarget.elements
    const username = form.username.value
    const password = form.password.value

    setAuthBusy(true)
    setLoginError('')
    try {
      const user = authMode === 'register'
        ? await register(username, password)
        : await signIn(username, password, adminLogin)

      setCurrentUser(user)
      setUserRole(user.role)
      setCurrentScreen('home')
    } catch (error) {
      setLoginError(error.message)
    } finally {
      setAuthBusy(false)
    }
  }

  async function handleSignOut() {
    await signOut()
    resetUserState()
    setLoginError('')
    setAuthMode('signin')
    setCurrentScreen('login')
  }

  /*
    SEND A MESSAGE THROUGH THE BACKEND
    Shared by Conversation, Reflection Chat and Continue Session.
    The backend safety-checks the message, then saves it with the reply.
    - support: the reply shows the support resources under it
    - crisis:  the reviewed crisis reply is shown, and the Support & Crisis
               Resources screen opens (its Back button returns here)
    - error:   the safety check could not run (fail closed): nothing was saved
               or sent to the AI; the Safety Check Unavailable screen opens and
               the user's text is kept for Try Again
    Any other failure (AI unavailable, rate limit, length limit, network) appears
    as a notice in the conversation, nothing is saved, and the text is put back.
  */
  async function deliverMessage({ sessionId, userMessage, currentMessages, setList, setChecking, setInput }) {
    const withUserMessage = [...currentMessages, { role: 'user', text: userMessage }]
    setList(withUserMessage)
    setInput('')
    setChecking(true)

    try {
      const response = await sendMessageToBackend(sessionId, userMessage)

      if (response.status === 'error') {
        setList(currentMessages)
        setInput(userMessage)
        setReturnScreen(currentScreen)
        setCurrentScreen('safety-error')
        return false
      }

      setList([
        ...withUserMessage,
        { role: 'assistant', text: response.message, resources: response.resources }
      ])

      if (response.status === 'crisis') {
        setReturnScreen(currentScreen)
        setCurrentScreen('support-resources')
      }
      return true
    } catch (error) {
      console.error('Message request failed:', error)
      setList([...currentMessages, { role: 'notice', text: error.message }])
      setInput(userMessage)
      return false
    } finally {
      setChecking(false)
    }
  }

  // CONVERSATION: start a fresh conversation (a session is created on the first message)
  function startConversation() {
    setMessages([])
    setMessage('')
    setActiveConversationId(null)
    setCurrentScreen('conversation')
  }

  // REFLECTION: create a reflection session with the chosen prompt
  async function startReflection() {
    if (startingReflection) return

    setStartingReflection(true)
    setScreenNotice('')
    try {
      const session = await createSession({
        type: 'reflection',
        prompt: reflectionPrompt,
        title: `Reflection: ${reflectionPrompt}`
      })
      setSelectedSession(session)
      setConversationStarter(session.prompt)
      setReflectionMessages([])
      setReflectionMessage('')
      setPreviousScreen('reflection')
      setCurrentScreen('reflection-chat')
    } catch (error) {
      setScreenNotice(error.message)
    } finally {
      setStartingReflection(false)
    }
  }

  // HISTORY: load a saved session's messages, then continue it
  async function openSession(session) {
    if (openingSessionId || deletingSessionId) return

    setOpeningSessionId(session.id)
    setHistoryError('')
    try {
      const detail = await getSession(session.id)
      setSelectedSession(detail)
      setConversationStarter(detail.prompt || CONVERSATION_STARTER)
      setPreviousScreen('history')

      if (detail.type === 'reflection') {
        setReflectionMessages(detail.messages)
        setReflectionMessage('')
        setCurrentScreen('reflection-chat')
      } else {
        setContinueMessages(detail.messages)
        setContinueMessage('')
        setCurrentScreen('continue-session')
      }
    } catch (error) {
      setHistoryError(error.message)
    } finally {
      setOpeningSessionId(null)
    }
  }

  // HISTORY: delete a session and its messages (DELETE /api/sessions/{id})
  async function removeSession(session) {
    if (openingSessionId || deletingSessionId) return
    if (!window.confirm(`Delete "${session.title}"? This removes the conversation permanently.`)) return

    setDeletingSessionId(session.id)
    setHistoryError('')
    try {
      await deleteSession(session.id)
      setConversationSessions((current) => current.filter((item) => item.id !== session.id))
      if (activeConversationId === session.id) {
        setActiveConversationId(null)
        setMessages([])
      }
    } catch (error) {
      setHistoryError(error.message)
    } finally {
      setDeletingSessionId(null)
    }
  }

  // END SESSION (support and safety-error screens): leave every open conversation.
  // The messages are already saved, so they stay available in History.
  function endSession() {
    setMessages([])
    setMessage('')
    setActiveConversationId(null)
    setReflectionMessages([])
    setReflectionMessage('')
    setContinueMessages([])
    setContinueMessage('')
    setSelectedSession(null)
    setSafetyChecking(false)
    setCurrentScreen('home')
  }

  // SUPPORT BAR (shown on every screen except the support page itself)
  // SAFETY INTEGRATION:
  // Opens the reviewed/static support page. No AI and no backend call is needed,
  // so it keeps working even if the safety service is down.
  const openSupport = () => {
    // From the safety-error screen, keep pointing at the conversation it came from.
    if (currentScreen !== 'safety-error') {
      setReturnScreen(currentScreen)
    }
    // Stop the breathing exercise so it doesn't keep running in the background
    setBreathingActive(false)
    setBreathingPhase('Inhale')
    setBreathingCount(4)
    setCurrentScreen('support-resources')
  }

  const supportBar = (
    <button className='support-bar' type='button' onClick={openSupport}>
      Need support now? <strong>Get help</strong>
    </button>
  )



  // LOADING SCREEN (while a saved sign-in is checked)
  if (currentScreen === 'loading') {
    return (
      <div className='app'>
        {supportBar}
        <main className='login-page'>
          <section className='login-card'>
            <p className='status-text' role='status'>Loading...</p>
          </section>
        </main>
      </div>
    )
  }

  // LOGIN SCREEN
  if (currentScreen === 'login') {
    const registering = authMode === 'register'
    return (
      <div className='app'>
        {supportBar}
        <main className='login-page' >
          <section className='login-card'>
            <h1>AI COMPANION FOR EMOTIONAL WELLNESS & SELF-REFLECTION</h1>

            <p className='subtitle'>
              A safety aware AI Companion for reflection and non-clinical emotional support.
            </p>

            <div className='notice'>
              <strong>Before you begin</strong>
              <p>
                This AI Companion is not a replacement for professional therapy or medical care.
              </p>
            </div>

            {/* AUTHENTICATION
                The server checks the credentials and returns the account's role.
                With "Sign in as Administrator" checked, a non-admin account is
                refused (403) and the person stays on this screen. */}
            <form className='login-form' onSubmit={handleAuthSubmit}>

              <label htmlFor='username'>Username</label>
              <input
                id='username'
                type='text'
                autoComplete='username'
                minLength={registering ? 3 : undefined}
                maxLength={32}
                placeholder={registering ? 'Choose a username' : 'Enter your username'} required />

              {registering && (
                <p className='form-hint'>
                  3-32 letters, numbers, dots, dashes or underscores. Please don't use your real name or email.
                </p>
              )}

              <label htmlFor='password'>Password</label>
              <input
                id='password'
                type='password'
                autoComplete={registering ? 'new-password' : 'current-password'}
                minLength={registering ? 8 : undefined}
                maxLength={128}
                placeholder={registering ? 'At least 8 characters' : 'Enter your password'} required />

              {!registering && (
                <label className='login-admin-option' htmlFor='admin-login'>
                  <input
                    id='admin-login'
                    type='checkbox'
                    checked={adminLogin}
                    onChange={(event) => {
                      setAdminLogin(event.target.checked)
                      setLoginError('')
                    }}
                  />
                  Sign in as Administrator
                </label>
              )}

              {loginError && (
                <p className='login-error' role='alert'>{loginError}</p>
              )}

              <button type='submit' disabled={authBusy}>
                {authBusy
                  ? 'Please wait...'
                  : registering ? 'Create Account' : 'Sign In'}
              </button>
            </form>

            <p className='login-switch'>
              {registering ? 'Already have an account?' : 'New here?'}{' '}
              <button
                className='link-button'
                type='button'
                onClick={() => {
                  setAuthMode(registering ? 'signin' : 'register')
                  setAdminLogin(false)
                  setLoginError('')
                }}
              >
                {registering ? 'Sign in' : 'Create an account'}
              </button>
            </p>

            <p className='demo-note'>
              No email or real name is needed. Your account is only used to keep your sessions private.
            </p>

          </section>
        </main>
      </div>
    )
  }

  // HOME SCREEN
  if (currentScreen === 'home') {
    return (
      <div className='app'>
        {supportBar}

        <main className='home-page'>

          {/* REGULAR USER HOME
            Everything inside this section is hidden for admins. */}

          {userRole !== 'admin' && (
            <>
              <header className='home-header'>
                <div>
                  <h1>
                    AI COMPANION FOR EMOTIONAL WELLNESS & SELF-REFLECTION
                  </h1>

                  <p>
                    Welcome{currentUser ? `, ${currentUser.username}` : ''}! Take a moment for yourself today.
                  </p>
                </div>

                <button
                  className='logout-button'
                  type='button'
                  onClick={handleSignOut}
                >
                  Sign Out
                </button>
              </header>


              <section className='welcome-card'>

                <h2>
                  What would you like to do today
                </h2>

                <p>
                  Choose an option below to reflect, chat or use a guided coping tool.
                </p>


                <div className='home-options'>

                  {/* REGULAR USER OPTIONS */}

                  <button
                    className='home-option'
                    onClick={startConversation}
                  >
                    <span className='option-title'>
                      Start a Conversation
                    </span>

                    <span className='option-description'>
                      Talk through what's on your mind.
                    </span>
                  </button>


                  <button
                    className='home-option'
                    onClick={() => setCurrentScreen('reflection')}
                  >
                    <span className='option-title'>
                      Reflection Prompt
                    </span>

                    <span className='option-description'>
                      Use a prompt to pause and reflect.
                    </span>
                  </button>


                  <button
                    className='home-option'
                    onClick={() => setCurrentScreen('coping-tools')}
                  >
                    <span className='option-title'>
                      Coping Tools
                    </span>

                    <span className='option-description'>
                      Explore guided breathing, journaling and grounding tools.
                    </span>
                  </button>


                  <button
                    className='home-option'
                    onClick={() => setCurrentScreen('history')}
                  >
                    <span className='option-title'>
                      Conversation History
                    </span>

                    <span className='option-description'>
                      View and continue previous sessions.
                    </span>
                  </button>


                  <button
                    className='home-option'
                    onClick={() => setCurrentScreen('analytics')}
                  >
                    <span className='option-title'>
                      My Insights
                    </span>

                    {/* USER ANALYTICS: sample data until GET /api/analytics/me exists */}

                    <span className='option-description'>
                      View your session activity and usage patterns.
                    </span>
                  </button>

                </div>
              </section>
            </>
          )}


          {/* ADMIN HOME
            Only administrators see this section.
            Regular user Home content is completely hidden. */}

          {userRole === 'admin' && (
            <>
              <header className='home-header'>
                <div>
                  <h1>Admin Home</h1>

                  <p>
                    System administration and monitoring.
                  </p>
                </div>

                <button
                  className='logout-button'
                  type='button'
                  onClick={handleSignOut}
                >
                  Sign Out
                </button>
              </header>


              <section className='welcome-card'>

                <h2>
                  Administration
                </h2>

                <p>
                  View aggregate system usage, safety, and
                  application health statistics.
                </p>


                <div className='home-options'>

                  <button
                    className='home-option'
                    onClick={() => setCurrentScreen('admin')}
                  >
                    <span className='option-title'>
                      Admin Statistics
                    </span>

                    <span className='option-description'>
                      View system usage, safety, and application
                      health statistics.
                    </span>
                  </button>

                </div>

              </section>
            </>
          )}


          {/* DISCLAIMER */}

          <section className='home-disclaimer'>
            <strong>Non-clinical support:</strong> This AI companion
            is not a replacement for professional therapy or medical care.
          </section>

        </main>
      </div>
    )
  }

  // CONVERSATION SCREEN
  if (currentScreen === 'conversation') {
    return (
      <div className='app'>
        {supportBar}
        <main className='conversation-page'>

          <header className='conversation-header'>
            <button
              className='back-button'
              type='button'
              onClick={() => setCurrentScreen('home')}
            >
              Back to Home
            </button>

            <h1>Conversation</h1>
          </header>

          <section className='conversation-card'>

            <div className='conversation-notice'>
              <strong>Non-clinical support</strong>
              <p>
                This AI companion provides reflective, non-clinical support.
                It does not provide diagnosis, medical advice or treatment recommendations.
              </p>
            </div>

            <div className='message-area'>

              <div className='message assistant-message'>
                <span className='message-label'>AI Companion</span>
                <p>{CONVERSATION_STARTER}</p>
              </div>

              {messages.map((item, index) => (
                <MessageBubble key={item.id ? `saved-${item.id}` : `new-${index}`} item={item} />
              ))}

              {safetyChecking && (
                <div className='message assistant-message'>
                  <span className='message-label'>Safety Check</span>
                  <p>Checking your message before continuing...</p>
                </div>
              )}
              <div className='message-end' ref={messageEndRef} />

            </div>

            <form
              className='message-form'
              onSubmit={async (event) => {
                event.preventDefault()

                // Do not submit empty messages
                // Do not submit while a request is running
                if (!message.trim() || safetyChecking) {
                  return
                }

                const userMessage = message.trim()

                // The first message creates the conversation session (POST /api/sessions).
                let sessionId = activeConversationId
                const createdNow = !sessionId
                if (createdNow) {
                  setSafetyChecking(true)
                  try {
                    const session = await createSession({ type: 'conversation', prompt: CONVERSATION_STARTER })
                    sessionId = session.id
                    setActiveConversationId(sessionId)
                  } catch (error) {
                    setSafetyChecking(false)
                    setMessages([...messages, { role: 'notice', text: error.message }])
                    return
                  }
                }

                const delivered = await deliverMessage({
                  sessionId,
                  userMessage,
                  currentMessages: messages,
                  setList: setMessages,
                  setChecking: setSafetyChecking,
                  setInput: setMessage
                })

                // Nothing was saved, so don't leave an empty session behind; the next
                // attempt creates a new one. (The backend also hides and cleans up empty sessions.)
                if (createdNow && !delivered) {
                  setActiveConversationId(null)
                  deleteSession(sessionId).catch(() => {})
                }
              }}
            >

              <label
                htmlFor='message'
                className='sr-only'
              >
                Message
              </label>

              <input
                id='message'
                type='text'
                placeholder="What's on your mind today?"
                maxLength={MAX_MESSAGE_LENGTH}
                value={message}
                onChange={(event) => setMessage(event.target.value)}
                disabled={safetyChecking}
              />

              <button
                type='submit'
                disabled={safetyChecking}
              >
                {safetyChecking ? 'Checking...' : 'Send'}
              </button>

            </form>

            <p className='conversation-footer'>
              Your messages are screened for potential safety concerns before a response is generated
            </p>

          </section>
        </main>
      </div>
    )
  }

  // REFLECTION PROMPT SCREEN
  if (currentScreen === 'reflection') {
    return (
      <div className='app'>
        {supportBar}

        <main className='reflection-page'>
          <header className='reflection-header'>
            <button
              className='back-button'
              onClick={() => setCurrentScreen('home')}
            >
              Back to Home
            </button>

            <h1>Reflection Prompt</h1>
          </header>

          <section className='reflection-card'>
            <p className='reflection-intro'>
              Take a moment for yourself.
            </p>

            <div className='reflection-prompt-box'>
              <p>{reflectionPrompt}</p>
            </div>

            <div className='reflection-actions'>
              <button
                className='primary-button'
                type='button'
                disabled={startingReflection}
                onClick={startReflection}
              >
                {startingReflection ? 'Starting...' : 'Use This Prompt'}
              </button>

              <button
                className='secondary-button'
                onClick={() => {
                  let newPrompt

                  do {
                    const randomIndex = Math.floor(
                      Math.random() * reflectionPrompts.length
                    )

                    newPrompt = reflectionPrompts[randomIndex]
                  } while (
                    reflectionPrompts.length > 1 &&
                    newPrompt === reflectionPrompt
                  )

                  setReflectionPrompt(newPrompt)
                }}
              >
                Give Me Another Prompt
              </button>
            </div>

            {screenNotice && (
              <p className='login-error' role='alert'>{screenNotice}</p>
            )}
          </section>
        </main>
      </div>
    )
  }


  // REFLECTION CHAT SCREEN
  if (currentScreen === 'reflection-chat') {
    return (
      <div className='app'>
        {supportBar}

        <main className='conversation-page'>
          <header className='conversation-header'>
            <button
              className='back-button'
              type='button'
              onClick={() => setCurrentScreen(previousScreen === 'history' ? 'history' : 'reflection')}
            >
              {previousScreen === 'history' ? 'Back to History' : 'Back to Reflection'}
            </button>

            <h1>Reflection Chat</h1>
          </header>

          <section className='conversation-card'>
            <div className='conversation-notice'>
              <strong>Guided self-reflection</strong>
              <p>
                Use this space to explore your thoughts and feelings.
                This AI companion provides reflective, non-clinical support.
                It does not provide diagnosis, medical advice or treatment
                recommendations.
              </p>
            </div>

            <div className='message-area'>
              {/* Display the selected reflection prompt */}
              <div className='message assistant-message'>
                <span className='message-label'>Reflection Prompt</span>
                <p>
                  {selectedSession
                    ? selectedSession.prompt
                    : conversationStarter}
                </p>
              </div>

              {/* Display reflection chat messages */}
              {reflectionMessages.map((item, index) => (
                <MessageBubble key={item.id ? `saved-${item.id}` : `new-${index}`} item={item} />
              ))}

              {reflectionSafetyChecking && (
                <div className='message assistant-message'>
                  <span className='message-label'>Safety Check</span>
                  <p>Checking your message before continuing...</p>
                </div>
              )}
              <div className='message-end' ref={messageEndRef} />
            </div>

            <form
              className='message-form'
              onSubmit={async (event) => {
                event.preventDefault()

                if (
                  !reflectionMessage.trim() ||
                  reflectionSafetyChecking ||
                  !selectedSession
                ) {
                  return
                }

                await deliverMessage({
                  sessionId: selectedSession.id,
                  userMessage: reflectionMessage.trim(),
                  currentMessages: reflectionMessages,
                  setList: setReflectionMessages,
                  setChecking: setReflectionSafetyChecking,
                  setInput: setReflectionMessage
                })
              }}
            >
              <label
                htmlFor='reflection-message'
                className='sr-only'
              >
                Message
              </label>

              <input
                id='reflection-message'
                type='text'
                placeholder='Write your reflection...'
                maxLength={MAX_MESSAGE_LENGTH}
                value={reflectionMessage}
                onChange={(event) =>
                  setReflectionMessage(event.target.value)
                }
                disabled={reflectionSafetyChecking}
              />

              <button
                type='submit'
                disabled={reflectionSafetyChecking}
              >
                {reflectionSafetyChecking ? 'Checking...' : 'Send'}
              </button>
            </form>

            <p className='conversation-footer'>
              Your messages are screened for potential safety concerns
              before an AI response is generated.
            </p>
          </section>
        </main>
      </div>
    )
  }

  // COPING TOOLS SCREEN
  if (currentScreen === 'coping-tools') {
    return (
      <div className='app'>
        {supportBar}
        <main className='coping-tools-page'>

          <header className='coping-tools-header'>
            <button className='back-button'
              onClick={() => {
                // stop the breathing timer before leaving this screen
                setBreathingActive(false)
                setBreathingPhase('Inhale')
                setBreathingCount(4)
                setCurrentScreen('home')
              }}>Back to Home</button>
            <h1>Coping Tools</h1>
          </header>

          <section className='coping-tools-card'>
            <p className='coping-tools-intro'>Choose a guided activity for a brief moment of relaxation.</p>

            {/*MINDFUL BREATHING*/}
            <section className='coping-tool-section'>
              <h2>Mindful Breathing</h2>
              <p>Follow the breathing visual at a comfortable pace. Stop if the exercise feels uncomfortable.</p>

              {/*BOX BREATHING VISUAL*/}
              <div className='breathing-box-container'>
                <div className='breathing-ripple'
                  role='img'
                  aria-label='Box breathing guide'>

                  {/* RING 1*/}
                  <div className='ripple-ring fixed-ring'></div>

                  {/* RING 2*/}
                  <div className={`ripple-ring ${!breathingActive
                    ? 'ring-hidden'
                    : breathingPhase === 'Inhale'
                      ? breathingCount <= 3
                        ? 'ring-visible'
                        : 'ring-hidden'
                      : breathingPhase === 'Hold Full'
                        ? 'ring-visible'
                        : breathingPhase === 'Exhale'
                          ? breathingCount >= 2
                            ? 'ring-visible'
                            : 'ring-hidden'
                          : 'ring-hidden'
                    }`}
                  ></div>

                  {/* RING 3*/}
                  <div className={`ripple-ring ${!breathingActive
                    ? 'ring-hidden'
                    : breathingPhase === 'Inhale'
                      ? breathingCount <= 2
                        ? 'ring-visible'
                        : 'ring-hidden'
                      : breathingPhase === 'Hold Full'
                        ? 'ring-visible'
                        : breathingPhase === 'Exhale'
                          ? breathingCount >= 3
                            ? 'ring-visible'
                            : 'ring-hidden'
                          : 'ring-hidden'
                    }`}
                  ></div>

                  {/* RING 4*/}
                  <div className={`ripple-ring ${!breathingActive
                    ? 'ring-hidden'
                    : breathingPhase === 'Inhale'
                      ? breathingCount <= 1
                        ? 'ring-visible'
                        : 'ring-hidden'
                      : breathingPhase === 'Hold Full'
                        ? 'ring-visible'
                        : breathingPhase === 'Exhale'
                          ? breathingCount >= 4
                            ? 'ring-visible'
                            : 'ring-hidden'
                          : 'ring-hidden'
                    }`}
                  ></div>

                  {/* CENTER TEXT */}
                  <div className='breathing-center'>

                    {breathingActive ? (
                      <>
                        <strong>
                          {breathingPhase === 'Hold Full' ||
                            breathingPhase === 'Hold Empty'
                            ? 'Hold'
                            : breathingPhase}
                        </strong>

                        <span>{breathingCount}</span>
                      </>
                    ) : (
                      <>
                        <strong>Breathe</strong>
                      </>
                    )}

                  </div>

                </div>

              </div>


              {/* BREATHING INSTRUCTIONS */}
              <p className='breathing-instruction'>
                Inhale for 4 seconds → Hold for 4 seconds →
                Exhale for 4 seconds → Hold for 4 seconds
              </p>


              {/* BREATHING CONTROLS */}
              <div className='breathing-controls'>
                {!breathingActive ? (
                  <button
                    className='primary-button'
                    type='button'
                    onClick={() => {
                      setBreathingPhase('Inhale')
                      setBreathingCount(4)
                      setBreathingActive(true)
                    }}
                  >
                    Start Breathing
                  </button>

                ) : (

                  <button
                    className='secondary-button'
                    type='button'
                    onClick={() => {
                      recordCopingUsage('breathing')
                      setBreathingActive(false)
                      setBreathingPhase('Inhale')
                      setBreathingCount(4)
                    }}
                  >
                    Stop
                  </button>

                )}

              </div>

            </section>

            {/*JOURNALING*/}
            <section className='coping-tool-section'>
              <h2>Journaling</h2>
              <p>Use a prompt to pause and reflect on what's on your mind</p>
              <div className='journaling-prompt'>
                <strong>Reflection prompt</strong>
                <p>What has been taking up most of your energy lately?</p>
              </div>
              <form
                onSubmit={(event) => {
                  event.preventDefault()

                  if (!journalText.trim()) return

                  recordCopingUsage('journaling')
                  setJournalText('')
                  setJournalSaved(true)
                }}
              >
                <textarea
                  id='journal-entry'
                  value={journalText}
                  onChange={(event) => {
                    setJournalText(event.target.value)
                    setJournalSaved(false)
                  }}
                  placeholder='Write your thoughts here...'
                  rows={4}
                />

                <button className='primary-button' type='submit'>
                  Save Reflection Journal
                </button>
              </form>

              {journalSaved && (
                <p role='status'>
                  Reflection recorded for this prototype.
                </p>
              )}

            </section>

            {/* Grounding */}
            <section className='coping-tool-section'>
              <h2>Grounding</h2>
              <p>
                Bring your attention to the present moment by noticing what is around you
              </p>

              <div className='grounding-list'>
                <div>
                  <strong>5</strong>
                  <span>things you can see</span>
                </div>
                <div>
                  <strong>4</strong>
                  <span>things you can touch</span>
                </div>
                <div>
                  <strong>3</strong>
                  <span>things you can hear</span>
                </div>
                <div>
                  <strong>2</strong>
                  <span>things you can smell</span>
                </div>
                <div>
                  <strong>1</strong>
                  <span>things you can notice about your breathing</span>
                </div>
              </div>

              <div className='breathing-controls'>
                {!groundingStarted ? (
                  <button
                    className='primary-button'
                    type='button'
                    onClick={() => {
                      setGroundingStarted(true)
                    }}
                  >
                    Start Grounding
                  </button>
                ) : (
                  <button
                    className='primary-button'
                    type='button'
                    onClick={() => {
                      recordCopingUsage('grounding')
                      setGroundingStarted(false)

                    }}
                  >
                    Complete Grounding
                  </button>
                )}
              </div>
            </section>
          </section>
        </main >
      </div >
    )
  }

  // CONVERSATION HISTORY SCREEN
  // GET /api/sessions returns only the signed-in user's sessions.
  if (currentScreen === 'history') {
    return (
      <div className='app'>
        {supportBar}
        <main className='history-page'>

          <header className='history-header'>
            <button className='back-button'
              onClick={() => setCurrentScreen('home')}> Back to Home</button>
            <h1>Conversation History</h1>
            <p>View and continue your previous session conversations</p>
          </header>

          <section className='history-card'>
            <h2>Your Previous Conversations</h2>

            {screenLoading && (
              <p className='status-text' role='status'>Loading your conversations...</p>
            )}

            {(screenLoadError || historyError) && (
              <p className='login-error' role='alert'>{historyError || screenLoadError}</p>
            )}

            {!screenLoading && !screenLoadError && conversationSessions.length === 0 && (
              <p className='status-text'>
                No conversations yet. Your conversations and reflections will appear here.
              </p>
            )}

            <div className='session-list'>
              {conversationSessions.map((session) => (
                <div key={session.id}
                  className='session-item'>
                  <div className='session-information'>
                    <span className='session-date'>{session.date}</span>

                    <h3>{session.title}</h3>
                    <span className='session-count'>
                      {session.messageCount} {session.messageCount === 1 ? 'message' : 'messages'}
                    </span>

                  </div>

                  <div className='session-actions'>
                    <button
                      className='session-button'
                      type='button'
                      disabled={openingSessionId !== null || deletingSessionId !== null}
                      onClick={() => openSession(session)}
                    >
                      {openingSessionId === session.id ? 'Opening...' : 'Continue'}
                    </button>

                    <button
                      className='session-delete-button'
                      type='button'
                      aria-label={`Delete ${session.title}`}
                      disabled={openingSessionId !== null || deletingSessionId !== null}
                      onClick={() => removeSession(session)}
                    >
                      {deletingSessionId === session.id ? 'Deleting...' : 'Delete'}
                    </button>
                  </div>

                </div>
              ))}
            </div>
          </section>
        </main>
      </div>
    )
  }
  // MY ANALYTICS SCREEN
  // BACKEND INTEGRATION:
  // Replace SAMPLE_ANALYTICS with GET /analytics/me for the authenticated user.
  // The backend must enforce user-level data isolation.
  // The frontend is never the security boundary.

  if (currentScreen === 'analytics') {
    const analytics = {
  ...SAMPLE_ANALYTICS,
  tools: [
    {
      name: 'Mindful Breathing',
      completed: copingUsage.breathing
    },
    {
      name: 'Journaling',
      completed: copingUsage.journaling
    },
    {
      name: 'Grounding',
      completed: copingUsage.grounding
    }
  ]
}

    const maxDayCount = Math.max(
      1,
      ...analytics.weekdays.map((item) => item.count)
    )

    const timesText = (count) =>
      `${count} ${count === 1 ? 'time' : 'times'}`

    return (
      <div className='app'>

        {supportBar}

        <main className='analytics-page'>

          {/* ANALYTICS HEADER */}
          <header className='analytics-header'>

            <button
              className='back-button'
              type='button'
              onClick={() => setCurrentScreen('home')}
            >
              Back to Home
            </button>

            <h1>My Insights</h1>

            <p>
              View your conversation activity and usage patterns
            </p>

          </header>


          {/* ANALYTICS CONTENT */}

          {analytics.totalSessions === 0 ? (

            <section className='analytics-card'>

              <h2>Your Activity</h2>

              <p className='analytics-empty'>
                No sessions yet. After your first session your activity
                will appear here.
              </p>

            </section>

          ) : (

            <>

              {/* ACTIVITY SUMMARY */}

              <section className='analytics-card'>

                <h2>Your Activity</h2>

                <p>
                  Here is a summary of your activity with the AI Companion.
                </p>

                <p className='analytics-takeaway'>
                  You checked in {timesText(analytics.sessionsThisWeek)} this week.
                </p>


                <div className='analytics-summary-grid'>

                  <article className='analytics-stat-card'>

                    <span className='analytics-stat-label'>
                      Total Sessions
                    </span>

                    <strong className='analytics-stat-number'>
                      {analytics.totalSessions}
                    </strong>

                    <span className='analytics-stat-description'>
                      Since you joined
                    </span>

                  </article>


                  <article className='analytics-stat-card'>

                    <span className='analytics-stat-label'>
                      Sessions This Week
                    </span>

                    <strong className='analytics-stat-number'>
                      {analytics.sessionsThisWeek}
                    </strong>

                    <span className='analytics-stat-description'>
                      Since Monday
                    </span>

                  </article>


                  <article className='analytics-stat-card'>

                    <span className='analytics-stat-label'>
                      Sessions This Month
                    </span>

                    <strong className='analytics-stat-number'>
                      {analytics.sessionsThisMonth}
                    </strong>

                    <span className='analytics-stat-description'>
                      Since the 1st of the month
                    </span>

                  </article>

                </div>

              </section>


              {/* SESSION FREQUENCY */}

              <section className='analytics-card'>

                <h2>Session Frequency</h2>

                <p className='analytics-intro'>
                  Your session activity by day of the week.
                </p>

                <div className='frequency-chart'>

                  {analytics.weekdays.map((item) => (

                    <div
                      className='frequency-row'
                      key={item.day}
                    >

                      <span>{item.day}</span>

                      <div
                        className='frequency-bar'
                        aria-hidden='true'
                      >

                        <div
                          className={`frequency-bar-fill${item.count === maxDayCount
                            ? ' is-peak'
                            : ''
                            }`}
                          style={{
                            width: `${(item.count / maxDayCount) * 100}%`
                          }}
                        ></div>

                      </div>

                      <strong>{item.count}</strong>

                    </div>

                  ))}

                </div>

              </section>


              {/* YOUR VISITS */}

              <section className='analytics-card'>

                <h2>Your Visits</h2>

                <div className='analytics-detail-grid'>

                  <div className='analytics-detail-item'>

                    <span>Last visit</span>

                    <strong>
                      {analytics.lastVisit}
                    </strong>

                  </div>


                  <div className='analytics-detail-item'>

                    <span>Typical session length</span>

                    <strong>
                      {analytics.typicalSessionMinutes} min
                    </strong>

                  </div>

                </div>

              </section>


              {/* COPING TOOL ACTIVITY */}

              <section className='analytics-card'>

                <h2>Coping Tool Activity</h2>

                <p className='analytics-intro'>
                  Guided exercises you have completed.
                </p>


                <div className='tool-usage-list'>

                  {analytics.tools.map((tool) => (

                    <div
                      className='tool-usage-item'
                      key={tool.name}
                    >

                      <span>
                        {tool.name}
                      </span>

                      <strong>
                        {tool.completed} completed
                      </strong>

                    </div>

                  ))}

                </div>


                {/* PRIVACY NOTE */}

                <section className='analytics-privacy-note'>

                  <strong>Your activity is private</strong>

                  <p>
                    This information is intended to help you understand
                    your own usage of the AI Companion. You can only view
                    analytics associated with your authenticated account.
                  </p>

                </section>

              </section>

            </>

          )}

        </main>

      </div>
    )
  }

  // ADMIN DASHBOARD
  // BACKEND INTEGRATION:
  // Data from GET /api/admin/analytics, /api/admin/logs and /api/health (admin-only).
  //
  // IMPORTANT:
  // The backend verifies that the authenticated user is an admin.
  // The frontend is not the security boundary and role checking here is only for prototype UI.
  // Raw conversation messages are never displayed here.

  if (currentScreen === 'admin' && userRole === 'admin') {

    const adminAnalytics = adminAnalyticsData || EMPTY_ADMIN_ANALYTICS
    const aiUsage = adminAnalytics.aiUsage

    // Architecture Health: this page loaded, so the frontend is healthy; the other
    // layers (API, database, logging, safety, AI) come from GET /api/health.
    const architectureHealth = [
      { name: 'Frontend', status: 'Healthy' },
      ...healthServices
    ]

    const maxDayCount = Math.max(
      1,
      ...adminAnalytics.weekdays.map((item) => item.count)
    )
    const maxDayTokens = Math.max(1, ...aiUsage.daily.map((item) => item.inputTokens + item.outputTokens))
    const maxDayCost = Math.max(0.000001, ...aiUsage.daily.map((item) => item.cost))

    return (
      <div className='app'>

        <main className='analytics-page'>

          <header className='analytics-header'>

            <button
              className='back-button'
              type='button'
              onClick={() => setCurrentScreen('home')}
            >
              Back to Home
            </button>

            <h1>Admin Dashboard</h1>

            <p>
              System usage, safety monitoring, and application health
            </p>

            {screenLoading && (
              <p className='status-text' role='status'>Loading dashboard data...</p>
            )}

          </header>


          {/*  OVERVIEW */}

          <section className='analytics-card'>

            <h2>Overview: Last 7 Days</h2>

            <p className='analytics-intro'>
              Aggregate activity across all users.
              Conversation content is not shown here.
            </p>


            <div className='analytics-summary-grid'>

              <article className='analytics-stat-card'>

                <span className='analytics-stat-label'>
                  Active Users
                </span>

                <strong className='analytics-stat-number'>
                  {adminAnalytics.activeUsers}
                </strong>

                <span className='analytics-stat-description'>
                  Users with activity
                </span>

              </article>


              <article className='analytics-stat-card'>

                <span className='analytics-stat-label'>
                  Total Sessions
                </span>

                <strong className='analytics-stat-number'>
                  {adminAnalytics.totalSessions}
                </strong>

                <span className='analytics-stat-description'>
                  All users combined
                </span>

              </article>


              <article className='analytics-stat-card'>

                <span className='analytics-stat-label'>
                  Sessions per Active User
                </span>

                <strong className='analytics-stat-number'>
                  {adminAnalytics.sessionsPerUser}
                </strong>

                <span className='analytics-stat-description'>
                  Average over 7 days
                </span>

              </article>


              <article className='analytics-stat-card'>

                <span className='analytics-stat-label'>
                  Messages Safety-Checked
                </span>

                <strong className='analytics-stat-number'>
                  {adminAnalytics.messagesSafetyChecked}
                </strong>

                <span className='analytics-stat-description'>
                  Before AI processing
                </span>

              </article>


              <article className='analytics-stat-card is-alert'>

                <span className='analytics-stat-label'>
                  Safety Check Errors
                </span>

                <strong className='analytics-stat-number'>
                  {adminAnalytics.safetyCheckErrors}
                </strong>

                <span className='analytics-stat-description'>
                  Failed safety checks
                </span>

              </article>


              <article
                className={`analytics-stat-card${adminAnalytics.sentToAIUnchecked > 0
                  ? ' is-alert'
                  : ''
                  }`}
              >

                <span className='analytics-stat-label'>
                  Sent to AI Unchecked
                </span>

                <strong className='analytics-stat-number'>
                  {adminAnalytics.sentToAIUnchecked}
                </strong>

                <span className='analytics-stat-description'>
                  Should always be 0
                </span>

              </article>

            </div>

          </section>

          {/* COST & AI USAGE */}

          <section className='analytics-card'>

            <h2>Cost &amp; AI Usage</h2>

            <p className='analytics-intro'>
              AI token consumption and estimated cost over the last 7 days
              ({aiUsage.configured ? `model: ${aiUsage.model}` : 'AI not configured'}).
              Crisis and support templates use no AI, so they cost nothing.
            </p>

            <div className='analytics-summary-grid'>

              <article className='analytics-stat-card'>
                <span className='analytics-stat-label'>Estimated AI Cost</span>
                <strong className='analytics-stat-number'>{formatUsd(aiUsage.estimatedCost)}</strong>
                <span className='analytics-stat-description'>
                  {formatUsd(aiUsage.avgCostPerRequest)} per AI reply on average
                </span>
              </article>

              <article className='analytics-stat-card'>
                <span className='analytics-stat-label'>Total Tokens</span>
                <strong className='analytics-stat-number'>{formatNumber(aiUsage.totalTokens)}</strong>
                <span className='analytics-stat-description'>Input and output tokens</span>
              </article>

              <article className='analytics-stat-card'>
                <span className='analytics-stat-label'>AI Requests</span>
                <strong className='analytics-stat-number'>{formatNumber(aiUsage.requests)}</strong>
                <span className='analytics-stat-description'>
                  Average reply time {(aiUsage.avgLatencyMs / 1000).toFixed(1)} s
                </span>
              </article>

              <article className='analytics-stat-card'>
                <span className='analytics-stat-label'>Budget Utilization</span>
                <strong className='analytics-stat-number'>
                  {aiUsage.budgetUtilization === null ? '—' : `${aiUsage.budgetUtilization}%`}
                </strong>
                <span className='analytics-stat-description'>
                  {aiUsage.monthlyBudget === null
                    ? `No monthly budget set (${formatUsd(aiUsage.monthToDateCost)} this month)`
                    : `${formatUsd(aiUsage.monthToDateCost)} of ${formatUsd(aiUsage.monthlyBudget)} this month`}
                </span>
              </article>

            </div>

            {/* TOKEN CONSUMPTION AND COST PER DAY */}
            <h3 className='analytics-subheading'>Tokens per Day</h3>
            <div className='frequency-chart'>
              {aiUsage.daily.map((item) => (
                <div className='frequency-row' key={`tokens-${item.day}`}>
                  <span>{item.day}</span>
                  <div
                    className='frequency-bar token-bar'
                    role='img'
                    aria-label={`${item.inputTokens} input and ${item.outputTokens} output tokens`}
                  >
                    <div
                      className='token-bar-input'
                      style={{ width: `${(item.inputTokens / maxDayTokens) * 100}%` }}
                    ></div>
                    <div
                      className='token-bar-output'
                      style={{ width: `${(item.outputTokens / maxDayTokens) * 100}%` }}
                    ></div>
                  </div>
                  <strong>{formatNumber(item.inputTokens + item.outputTokens)}</strong>
                </div>
              ))}
            </div>
            <p className='chart-legend'>
              <span className='legend-swatch token-bar-input'></span> Input tokens
              <span className='legend-swatch token-bar-output'></span> Output tokens
            </p>

            <h3 className='analytics-subheading'>Estimated Cost per Day</h3>
            <div className='frequency-chart'>
              {aiUsage.daily.map((item) => (
                <div className='frequency-row' key={`cost-${item.day}`}>
                  <span>{item.day}</span>
                  <div className='frequency-bar' aria-hidden='true'>
                    <div
                      className='frequency-bar-fill'
                      style={{ width: `${(item.cost / maxDayCost) * 100}%` }}
                    ></div>
                  </div>
                  <strong>{formatUsd(item.cost)}</strong>
                </div>
              ))}
            </div>

            <div className='tool-usage-list'>

              <div className='tool-usage-item'>
                <span>Input Tokens</span>
                <strong>{formatNumber(aiUsage.inputTokens)}</strong>
              </div>

              <div className='tool-usage-item'>
                <span>Output Tokens</span>
                <strong>{formatNumber(aiUsage.outputTokens)}</strong>
              </div>

              {aiUsage.byModel.length === 0 && (
                <div className='tool-usage-item'>
                  <span>Cost by AI Model</span>
                  <strong>No AI requests yet</strong>
                </div>
              )}

              {aiUsage.byModel.map((item) => (
                <div className='tool-usage-item' key={item.model}>
                  <span>Cost by AI Model: {item.model}</span>
                  <strong>{formatUsd(item.cost_usd)} ({formatNumber(item.requests)} requests)</strong>
                </div>
              ))}

              <div className='tool-usage-item'>
                <span>Replies Without AI (reviewed templates)</span>
                <strong>{formatNumber(aiUsage.repliesWithoutAI)}</strong>
              </div>

              <div className='tool-usage-item'>
                <span>RAG and Embedding Usage</span>
                <strong>Not used</strong>
              </div>

            </div>

          </section>


          {/*  SESSION FREQUENCY */}

          <section className='analytics-card'>

            <h2>Session Frequency</h2>

            <p className='analytics-intro'>
              Sessions per day over the last 7 days.
            </p>


            <div className='frequency-chart'>

              {adminAnalytics.weekdays.map((item) => (

                <div
                  className='frequency-row'
                  key={item.day}
                >

                  <span>
                    {item.day}
                  </span>


                  <div
                    className='frequency-bar'
                    aria-hidden='true'
                  >

                    <div
                      className='frequency-bar-fill'
                      style={{
                        width: `${(item.count / maxDayCount) * 100}%`
                      }}
                    ></div>

                  </div>


                  <strong>
                    {item.count}
                  </strong>

                </div>

              ))}

            </div>

          </section>


          {/* ESCALATIONS */}

          <section className='analytics-card'>

            <h2>Escalations</h2>

            <p className='analytics-intro'>
              Safety concerns routed to additional support during
              the last 7 days.
            </p>


            <div className='analytics-summary-grid'>

              <article className='analytics-stat-card'>

                <span className='analytics-stat-label'>
                  Total Escalations
                </span>

                <strong className='analytics-stat-number'>
                  {adminAnalytics.escalations}
                </strong>

                <span className='analytics-stat-description'>
                  Routed to support resources
                </span>

              </article>

              <article className='analytics-stat-card'>
                <span className='analytics-stat-label'>Crisis</span>
                <strong className='analytics-stat-number'>{adminAnalytics.crisisEscalations}</strong>
                <span className='analytics-stat-description'>Crisis screen and resources, no AI</span>
              </article>

              <article className='analytics-stat-card'>
                <span className='analytics-stat-label'>Support</span>
                <strong className='analytics-stat-number'>{adminAnalytics.supportEscalations}</strong>
                <span className='analytics-stat-description'>Reply shown with support resources</span>
              </article>

            </div>

          </section>


          {/* SAFETY DECISIONS */}

          <section className='analytics-card'>

            <h2>Safety Decisions</h2>

            <p className='analytics-intro'>
              Results from safety screening across all users.
              {' '}Sensitive topics answered with a boundary: {adminAnalytics.boundaryReplies}.
              AI replies blocked by the output check: {adminAnalytics.repliesBlocked}.
            </p>


            <div className='analytics-summary-grid'>

              <article className='analytics-stat-card'>

                <span className='analytics-stat-label'>
                  Clear
                </span>

                <strong className='analytics-stat-number'>
                  {adminAnalytics.safetyDecisions.clear}
                </strong>

                <span className='analytics-stat-description'>
                  Approved to continue
                </span>

              </article>


              <article className='analytics-stat-card'>

                <span className='analytics-stat-label'>
                  Concern
                </span>

                <strong className='analytics-stat-number'>
                  {adminAnalytics.safetyDecisions.concern}
                </strong>

                <span className='analytics-stat-description'>
                  Routed for additional support
                </span>

              </article>


              <article className='analytics-stat-card'>

                <span className='analytics-stat-label'>
                  Error
                </span>

                <strong className='analytics-stat-number'>
                  {adminAnalytics.safetyDecisions.error}
                </strong>

                <span className='analytics-stat-description'>
                  Safety check failures
                </span>

              </article>

            </div>

          </section>


          {/* COPING TOOL ACTIVITY */}

          <section className='analytics-card'>

            <h2>Coping Tool Activity</h2>

            <p className='analytics-intro'>
              Completed guided exercises across all users.
              Sample data: coping-tool usage is not stored by the backend yet.
            </p>


            <div className='tool-usage-list'>

              {SAMPLE_COPING_TOOLS.map((tool) => (

                <div
                  className='tool-usage-item'
                  key={tool.name}
                >

                  <span>
                    {tool.name}
                  </span>

                  <strong>
                    {tool.completed} completed
                  </strong>

                </div>

              ))}

            </div>

          </section>


          {/*ARCHITECTURE HEALTH */}

          <section className='analytics-card'>

            <h2>Architecture Health</h2>

            <p className='analytics-intro'>
              Current health of the main application layers.
            </p>


            <div className='admin-health-list'>

              {screenLoading && (
                <p className='status-text' role='status'>Checking services...</p>
              )}

              {!screenLoading && architectureHealth.map((layer) => (

                <div
                  className='admin-health-item'
                  key={layer.name}
                >

                  <span>
                    {layer.name}
                  </span>

                  <strong>
                    {layer.status}{layer.detail ? ` (${layer.detail})` : ''}
                  </strong>

                </div>

              ))}

            </div>

          </section>


          {/*  RECENT LOG EVENTS */}

          <section className='analytics-card'>

            <h2>Recent Log Events</h2>

            <p className='analytics-intro'>
              Recent operational and safety events.
              Raw user messages are not displayed.
            </p>


            <div className='admin-log-list'>

              {screenLoading && (
                <p className='status-text' role='status'>Loading recent events...</p>
              )}

              {screenLoadError && (
                <p className='login-error' role='alert'>{screenLoadError}</p>
              )}

              {!screenLoading && !screenLoadError && recentLogs.length === 0 && (
                <p className='status-text'>No events recorded yet.</p>
              )}

              {recentLogs.map((log, index) => (

                <div
                  className={`admin-log-item ${log.status === 'Warning'
                    ? 'is-warning'
                    : log.status === 'Error'
                      ? 'is-error'
                      : ''
                    }`}
                  key={`${log.time}-${index}`}
                >

                  <div>

                    <span>
                      {formatLogTime(log.time)} · {log.type}
                    </span>

                    <strong>
                      {log.message}
                    </strong>

                  </div>

                  <span>
                    {log.status}
                  </span>

                </div>

              ))}

            </div>

          </section>


          {/* ADMIN PRIVACY NOTE */}

          <section className='analytics-privacy-note'>

            <strong>
              Restricted to administrators
            </strong>

            <p>
              This dashboard shows aggregate system and safety information.
              Individual users and raw conversation messages are not
              displayed here.
            </p>

          </section>


        </main>

      </div>
    )
  }


  // CONTINUE SESSION SCREEN

  if (currentScreen === 'continue-session') {
    return (
      <div className='app'>
        {supportBar}

        <main className='conversation-page'>
          <header className='conversation-header'>
            <button
              className='back-button'
              type='button'
              onClick={() => setCurrentScreen('history')}
            >
              Back to History
            </button>

            <h1>
              {selectedSession
                ? selectedSession.title
                : 'Previous Conversation'}
            </h1>
          </header>


          {/* CONVERSATION CARD */}
          <section className='conversation-card'>
            <div className='conversation-notice'>
              <strong>Continue your conversation</strong>
              <p>
                Pick up where you left off and continue exploring
                your thoughts and feelings. This AI companion provides
                reflective, non-clinical support.
              </p>
            </div>

            <div className='message-area'>

              {/* Messages loaded with GET /api/sessions/{session_id} */}

              <div className='message assistant-message'>
                <span className='message-label'>Session Prompt</span>
                <p>
                  {selectedSession
                    ? selectedSession.prompt
                    : "Welcome back. Let's continue reflecting on this conversation."}
                </p>
              </div>


              {/* DISPLAY MESSAGES */}
              {continueMessages.map((item, index) => (
                <MessageBubble key={item.id ? `saved-${item.id}` : `new-${index}`} item={item} />
              ))}


              {/* SAFETY CHECK STATUS */}
              {continueSafetyChecking && (
                <div className='message assistant-message'>
                  <span className='message-label'>
                    Safety Check
                  </span>

                  <p>
                    Checking your message before continuing...
                  </p>
                </div>
              )}
              <div className='message-end' ref={messageEndRef} />
            </div>


            {/* MESSAGE FORM */}

            {/* Same send-and-save workflow as the Conversation screen */}

            <form
              className='message-form'
              onSubmit={async (event) => {
                event.preventDefault()

                // Do not submit empty messages
                // Do not submit while safety check is running
                if (
                  !continueMessage.trim() ||
                  continueSafetyChecking ||
                  !selectedSession
                ) {
                  return
                }

                await deliverMessage({
                  sessionId: selectedSession.id,
                  userMessage: continueMessage.trim(),
                  currentMessages: continueMessages,
                  setList: setContinueMessages,
                  setChecking: setContinueSafetyChecking,
                  setInput: setContinueMessage
                })
              }}
            >
              <label
                htmlFor='continue-message'
                className='sr-only'
              >
                Message
              </label>

              <input
                id='continue-message'
                type='text'
                placeholder='Write your message...'
                maxLength={MAX_MESSAGE_LENGTH}
                value={continueMessage}
                onChange={(event) =>
                  setContinueMessage(event.target.value)
                }
                disabled={continueSafetyChecking}
              />

              <button
                type='submit'
                disabled={continueSafetyChecking}
              >
                {continueSafetyChecking ? 'Checking...' : 'Send'}
              </button>
            </form>

            <p className='conversation-footer'>
              Your messages are screened for potential safety concerns
              before an AI response is generated.
            </p>
          </section>
        </main>
      </div>
    )
  }
  // SUPPORT & CRISIS RESOURCES
  // SAFETY INTEGRATION:
  // This is reviewed/static content. The backend safety layer
  // routes here when a potential safety concern is detected.
  // Do not generate crisis guidance dynamically with the AI.
  if (currentScreen === 'support-resources') {
    return (
      <div className='app'>
        <main className='support-page'>
          <section className='support-card'>
            <div className='support-icon'>!</div>
            <h1>Support & Crisis Resources</h1>
            <p className='support-message'>I'm not able to provide crisis counseling,
              but you deserve support from a qualified professional or trusted person.</p>

            <p className='support-description'>If you need immediate support, consider
              contacting one of the resources below or reaching out to someone you trust</p>

            {/* 988 */}
            <article className='support-resource'>
              <div className='support-resource-content'>
                <h2>988 Suicide & Crisis Lifeline</h2>

                <p>Call or text <strong>988</strong> to connect with the Suicide & Crisis Lifeline.</p>
              </div>
              <a className='support-resource-button' href='tel:988'>Call 988</a>
            </article>

            {/* CRISIS TEXT LINE */}
            <article className='support-resource'>
              <div className='support-resource-content'>
                <h2>Crisis Text Line</h2>

                <p>Text <strong>HOME</strong> to <strong>741741</strong> to connect with a trained Crisis Counselor.</p>
              </div>
              <a className='support-resource-button' href='sms:741741?body=Home'>Text HOME</a>
            </article>

            {/* 911 */}
            <article className='support-resource'>
              <div className='support-resource-content'>
                <h2>Emergency Services</h2>

                <p>If you are in immediate danger or need emergency assistance, contact <strong>911</strong>. </p>
              </div>
              <a className='support-resource-button' href='tel:911'>Call 911</a>
            </article>

            {/* Trusted Person */}
            <div className='trusted-person-box'>
              <h2>Reach Out to Someone You Trust</h2>

              <p>Consider contacting a trusted friend, family member, caregiver or someone who can support you.</p>
            </div>

            {/* GO BACK / END SESSION
                After a crisis reply the user can return to the conversation (the
                reply and resources are still there) or end the session. */}
            <div className='support-actions'>
              {returnScreen !== 'support-resources' && (
                <button className='primary-button'
                  type='button'
                  onClick={() => setCurrentScreen(returnScreen)}>
                  {CHAT_SCREENS.includes(returnScreen)
                    ? 'Back to Conversation'
                    : returnScreen === 'login' ? 'Back to Sign In' : 'Go Back'}
                </button>
              )}
              {currentUser && (
                <button className='secondary-button'
                  type='button'
                  onClick={endSession}>End Session
                </button>
              )}
            </div>
          </section>
        </main>
      </div>
    )
  }


  // SAFETY ERROR / FALLBACK SCREEN
  // SAFETY BACKEND INTEGRATION:
  // Used when the safety service cannot complete its check.
  // The system must fail closed and must NOT send the unchecked
  // message to the conversational AI.
  if (currentScreen === 'safety-error') {
    return (
      <div className='app'>
        {supportBar}
        <main className='support-page'>
          <section className='support-card'>
            <div className='support-icon'>!</div>
            <h1>Safety Check Temporarily Unavailable</h1>
            <p className='support-message'>I'm unable to complete the safety check right now,
              so I can't safely continue the conversation.</p>

            <p className='support-description'>You can try again, use a coping tool or end the session.</p>

            {/* CRISIS LINK
                Someone in distress during an outage still needs a way to reach help.
                Static content: no AI and no safety service needed. */}
            <div className='support-callout'>
              <h2>If you need support right now</h2>
              <p>
                You don't need to wait for this check. You can call or text 988
                (Suicide & Crisis Lifeline) at any time, or see more options.
              </p>
              <div className='support-callout-actions'>
                <a className='support-resource-button' href='tel:988'>Call 988</a>
                <button
                  className='secondary-button'
                  type='button'
                  onClick={openSupport}
                >
                  See all support options
                </button>
              </div>
            </div>

            <div className='support-actions'>
              <button
                className='primary-button'
                type='button'
                onClick={() => setCurrentScreen(CHAT_SCREENS.includes(returnScreen) ? returnScreen : 'conversation')}
              >
                Try Again
              </button>

              <button
                className='secondary-button'
                type='button'
                onClick={() => setCurrentScreen('coping-tools')}
              >
                Coping Tools
              </button>

              <button
                className='secondary-button'
                type='button'
                onClick={endSession}
              >
                End Session
              </button>

            </div>

            <p className='support-footer'>
              This AI Companion does not provide crisis counseling,
              diagnosis, medical advice, or treatment.
            </p>

          </section>
        </main>
      </div>
    )
  }


  // PLACEHOLDER FOR FUTURE SCREENS
  return (
    <div className="app">
      <main className="placeholder-page">
        <section className="placeholder-card">
          <h1>
            {currentScreen === 'conversation' && 'Conversation'}
            {currentScreen === 'reflection' && 'Reflection Prompt'}
            {currentScreen === 'coping-tools' && 'Coping Tools'}
            {currentScreen === 'history' && 'Conversation History'}
          </h1>

          <p>
            This screen will be built next.
          </p>

          <button
            className="primary-button"
            onClick={() => setCurrentScreen('home')}
          >
            Back to Home
          </button>
        </section>
      </main>
    </div>
  )

}


export default App
