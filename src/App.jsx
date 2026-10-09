// IT 7993 CAPSTONE - FALL 2026
//Title: AI COMPANION FOR EMOTIONAL WELLNESS & SELF-REFLECTION
//Project Sponsor: Capgemini America, Inc.
//Instructor: Dr. Ying Xie
//Team P05-01: Shaheed Campbell, Cynthia Lakshminarayanan, Emmanuel Kofi Mensah, Korey Owens, Akhil Sai Talluri


/*
============================================================
BACKEND / AI INTEGRATION MAP
============================================================

1. AUTHENTICATION
   Current: prototype login only.
   Later: React → FastAPI authentication → authenticated user/session.

2. CONVERSATIONS
   Current: messages live in React state.
   Later: POST /sessions and POST /sessions/{session_id}/messages.

3. SAFETY / MODERATION
   Current: setTimeout + hard-coded safetyResult.
   Later: React → FastAPI → safety/moderation service.
   Possible results: clear, concern, error.
   IMPORTANT: error must fail closed; do not send the unchecked
   message to the conversational AI.

4. CONVERSATIONAL AI
   Current: hard-coded mock response.
   Later: only safety-approved messages are sent to the AI service.
   AI response returns through the backend to React.

5. CONVERSATION HISTORY
   Current: sample conversationSessions array.
   Later: GET /sessions and GET /sessions/{session_id}.
   Only the authenticated user's sessions may be returned.

6. MESSAGE PERSISTENCE
   Current: React state only.
   Later: PostgreSQL stores sessions and messages.

7. ANALYTICS / OPERATIONAL LOGGING
   Current: sample implemented in this frontend.
   Later: backend records session ID, architecture layer,
   safety decision, status, errors, and approved operational metrics.
   Raw conversation messages should not be exposed in admin analytics.

8. COPING TOOLS
   Current: static frontend content.
   Later: these remain static/reviewed content and do not need
   conversational AI to generate the exercise.

============================================================
*/


import { useState, useEffect, useRef } from 'react'
import './App.css'

//MY ANALYTICS: Prototype Sample Data
//BACKEND INTEGRATION: replace with GET /analytics/me for the USer
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

// ADMIN DASHBOARD SAMPLE DATA
// BACKEND INTEGRATION:
// Replace this sample data with information returned by
// protected admin-only backend endpoints.
//
// IMPORTANT:
// The backend must verify the admin role.
// Do not display raw conversation messages or personal user information.

const SAMPLE_ADMIN_ANALYTICS = {
  activeUsers: 24,
  totalSessions: 41,
  sessionsPerUser: 1.7,

  messagesSafetyChecked: 286,
  safetyCheckErrors: 3,
  sentToAIUnchecked: 0,

  weekdays: [
    { day: 'Mon', count: 5 },
    { day: 'Tue', count: 8 },
    { day: 'Wed', count: 6 },
    { day: 'Thu', count: 9 },
    { day: 'Fri', count: 4 },
    { day: 'Sat', count: 5 },
    { day: 'Sun', count: 4 }
  ],

  escalations: 7,

  safetyDecisions: {
    clear: 276,
    concern: 7,
    error: 3
  },

  copingTools: [
    { name: 'Mindful Breathing', completed: 48 },
    { name: 'Grounding Exercise', completed: 31 },
    { name: 'Reflection Prompt', completed: 26 },
    { name: 'Journaling', completed: 19 }
  ],

  architectureHealth: [
    { name: 'Frontend', status: 'Healthy' },
    { name: 'Backend / API', status: 'Healthy' },
    { name: 'Safety / Moderation', status: 'Healthy' },
    { name: 'AI Service', status: 'Healthy' },
    { name: 'Database', status: 'Healthy' },
    { name: 'Analytics / Logging', status: 'Healthy' }
  ],

  recentLogs: [
    {
      time: '10:42 AM',
      type: 'Safety Check',
      message: 'Safety check completed',
      status: 'OK'
    },
    {
      time: '10:35 AM',
      type: 'Session',
      message: 'Conversation session completed',
      status: 'OK'
    },
    {
      time: '10:21 AM',
      type: 'Safety',
      message: 'Safety concern routed to support resources',
      status: 'Warning'
    },
    {
      time: '10:08 AM',
      type: 'System',
      message: 'AI service health check completed',
      status: 'OK'
    },
    {
      time: '09:54 AM',
      type: 'Error',
      message: 'Safety service request failed',
      status: 'Error'
    }
  ]
}


function App() {
  const [currentScreen, setCurrentScreen] = useState('login')
  const [adminLogin, setAdminLogin] = useState(false)
  const [loginError, setLoginError] = useState('')
  const [userRole, setUserRole] = useState(null)
  const [message, setMessage] = useState('')
  const [messages, setMessages] = useState([])
  const [selectedSession, setSelectedSession] = useState(null)
  // BACKEND INTEGRATION:
  // selectedSession will eventually come from the authenticated user's
  // saved sessions returned by the backend.
  const [safetyChecking, setSafetyChecking] = useState(false)
  // SAFETY BACKEND INTEGRATION:
  // Currently this is only a frontend loading state.
  // The real safety/moderation API will control the result.
  const [safetyStatus, setSafetyStatus] = useState('clear')
  // SAFETY BACKEND INTEGRATION:
  // Prototype values: clear, checking, concern, error.
  // The backend safety/moderation service will return the actual result.
  const [continueMessage, setContinueMessage] = useState('')
  const [continueMessages, setContinueMessages] = useState([])
  const [previousScreen, setPreviousScreen] = useState('home')
  const [continueSafetyChecking, setContinueSafetyChecking] = useState(false)
  const [conversationStarter, setConversationStarter] = useState('What would you like to talk about today')

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
  const [breathingActive, setBreathingActive] = useState(false)
  const [breathingPhase, setBreathingPhase] = useState('Inhale')
  const [breathingCount, setBreathingCount] = useState(4)
  const countRef = useRef(4)

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
  // BACKEND INTEGRATION:
  // Prototype/sample sessions only.
  // Replace this array with GET /sessions for the authenticated user.
  const conversationSessions = [
    {
      id: 1,
      date: 'September 28, 2026',
      title: 'Work and daily stress',
      messageCount: 8
    },
    {
      id: 2,
      date: 'September 26, 2026',
      title: 'Thinking through a difficult situation',
      messageCount: 12
    },
    {
      id: 3,
      date: 'September 24, 2026',
      title: 'Reflection on the week',
      messageCount: 6
    }
  ]

  // SUPPORT BAR (shown on every screen except the support page itself)
  // SAFETY INTEGRATION:
  // Opens the reviewed/static support page. No AI and no backend call is needed,
  // so it keeps working even if the safety service is down.
  const openSupport = () => {
    setPreviousScreen(currentScreen)
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

  // LOGIN SCREEN
  if (currentScreen === 'login') {
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

            <form
              className='login-form'
              onSubmit={(event) => {
                event.preventDefault()
                // BACKEND INTEGRATION:
                // Replace prototype navigation with real authentication.
                // Send credentials to FastAPI, including whether admin signin was requested.
                //  The server returns the user's role. If administrator
                // sign-in was requested and the role is not 'admin', the server must
                // answer 403 and the person stays on this screen.
                // navigate to Home only after successful authentication.

                const username = event.currentTarget.elements.username.value
                const isAdminAccount = username.trim().toLowerCase() === 'admin'// PROTOTYPE ONLY: the username "admin" stands in for an administrator account.


                // PROTOTYPE: If Administrator is checked, the username must be "admin".
                if (adminLogin && !isAdminAccount) {
                  setLoginError('Administrator sign-in was not successful')
                  return
                }
                setLoginError('')
                setUserRole(adminLogin ? 'admin' : 'user')
                setCurrentScreen('home')
              }} >

              <label htmlFor='username'>Username</label>
              <input
                id='username'
                type='text'
                //autoComplete='username'
                placeholder='Enter your username' required />

              <label htmlFor='password'>Password</label>
              <input
                id='password'
                type='password'
                //autoComplete='current-password'
                placeholder='Enter your password' required />

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

              {loginError && (
                <p className='login-error' role='alert'>{loginError}</p>
              )}

              <button type='submit'>Sign In</button>
            </form>


            <p className='demo-note'>
              Prototype Placeholder login '-' authentication to be connected to backend(?)
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
                    Welcome! Take a moment for yourself today.
                  </p>
                </div>

                <button
                  className='logout-button'
                  type='button'
                  onClick={() => {
                    setUserRole(null)
                    setAdminLogin(false)
                    setLoginError('')
                    setCurrentScreen('login')
                  }}
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
                    onClick={() => setCurrentScreen('conversation')}
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

                    {/* USER ANALYTICS */}
                    {/* BACKEND INTEGRATION:
                      Replace mock analytics data with the authenticated user's
                      analytics returned from the backend, for example:
                      GET /analytics/me
                  */}

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
                  onClick={() => {
                    setUserRole(null)
                    setAdminLogin(false)
                    setLoginError('')
                    setCurrentScreen('login')
                  }}
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
                <p>{conversationStarter}</p>
              </div>

              {messages.map((item, index) => (
                <div
                  key={index}
                  className={
                    item.role === 'user'
                      ? 'message user-message'
                      : 'message assistant-message'
                  }
                >
                  <span className='message-label'>
                    {item.role === 'user' ? 'You' : 'AI Companion'}
                  </span>

                  <p>{item.text}</p>
                </div>
              ))}

              {safetyChecking && (
                <div className='message assistant-message'>
                  <span className='message-label'>Safety Check</span>
                  <p>Checking your message before continuing...</p>
                </div>
              )}

            </div>

            <form
              className='message-form'
              onSubmit={(event) => {
                event.preventDefault()

                // Do not submit empty messages
                // Do not submit while safety check is running
                if (!message.trim() || safetyChecking) {
                  return
                }

                const userMessage = message.trim()
                // BACKEND INTEGRATION:
                // Send this message with the authenticated user/session
                // information to the backend after the safety workflow
                // is implemented server-side
                // Start safety check
                setSafetyChecking(true)
                setSafetyStatus('checking')

                // Add user's message
                setMessages((currentMessages) => [
                  ...currentMessages,
                  {
                    role: 'user',
                    text: userMessage
                  }
                ])

                // Clear input
                setMessage('')

                //============================================================
                // SAFETY BACKEND INTEGRATION:
                // Replace this setTimeout prototype with a request to FastAPI.
                // Intended flow:
                // React → FastAPI → Safety/Moderation → clear/concern/error
                // ============================================================
                setTimeout(() => {

                  // Temporary result
                  const safetyResult = 'clear' // Prototype only: change to'concern' or 'error' to view safety escalation and error fallback
                  // BACKEND INTEGRATION:
                  // Remove this hard-coded value and use the actual
                  // safety/moderation API response.
                  setSafetyStatus(safetyResult)
                  setSafetyChecking(false)

                  // If safety concern is detected
                  if (safetyResult === 'concern') {
                    setCurrentScreen('support-resources')
                    return
                  }

                  // If safety check fails
                  if (safetyResult === 'error') {
                    setSafetyStatus('error')
                    setMessages((currentMessages) => currentMessages.slice(0, -1))
                    setMessage(userMessage)
                    setCurrentScreen('safety-error')
                    return
                  }
                  //============================================================
                  // AI BACKEND INTEGRATION:
                  // This is currently a mock response.
                  // When integrated, only a safety-approved message should be
                  // sent to the conversational AI through FastAPI.
                  // AI response: backend → React.
                  // ============================================================
                  // If message is clear, show AI response
                  setMessages((currentMessages) => [
                    ...currentMessages,
                    {
                      role: 'assistant',
                      text: 'Is there something that happened today to make you feel like that?'
                    }
                  ])

                }, 1000)
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
              Your messages will be screened for potential safety concerns before a response is generated
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
            <button className='back-button'
              onClick={() => setCurrentScreen('home')}>Back to Home</button>
            <h1>Reflection Prompt</h1>
          </header>

          <section className='reflection-card'>
            <p className='reflection-intro'>Take a moment for yourself.</p>

            <div className='reflection-prompt-box'>
              <p>{reflectionPrompt}</p>
            </div>

            <div className='reflection-actions'>
              <button className='primary-button'
                onClick={() => {
                  setConversationStarter(reflectionPrompt)
                  setMessages([])
                  setCurrentScreen('conversation')
                }}> Use This Prompt</button>

              <button className='secondary-button'
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
                }}>Give Me Another Prompt</button>

            </div>
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
            </section>

            {/*Grounding*/}
            <section className='coping-tool-section'>
              <h2>Grounding</h2>
              <p>Bring your attention to the present moment by noticing what is around you</p>
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
            </section>
          </section>
        </main >
      </div >
    )
  }

  // CONVERSTAION HISTORY SCREEN
  // BACKEND INTEGRATION:
  // Replace the sample conversationSessions data with sessions
  // returned for the authenticated user by GET /sessions.
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
            <div className='session-list'>
              {conversationSessions.map((session) => (
                <div key={session.id}
                  className='session-item'>
                  <div className='session-information'>
                    <span className='session-date'>{session.date}</span>

                    <h3>{session.title}</h3>
                    <span className='session-count'>{session.messageCount} messages</span>

                  </div>

                  <button className='session-button'
                    onClick={() => {
                      setSelectedSession(session)
                      // BACKEND INTEGRATION:
                      // Load the selected session/messages with
                      // GET /sessions/{session_id}.

                      setCurrentScreen('continue-session')
                    }}>Continue</button>
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
    const analytics = SAMPLE_ANALYTICS

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
  // Replace SAMPLE_ADMIN_ANALYTICS with data returned by
  // protected admin-only backend endpoints.
  //
  // IMPORTANT:
  // The backend must verify that the authenticated user is an admin.
  // The frontend is not the security boundary and role checking here is only for prototype UI.
  // Do not display raw conversation messages here.

  if (currentScreen === 'admin' && userRole === 'admin') {

    const adminAnalytics = SAMPLE_ADMIN_ANALYTICS

    const maxDayCount = Math.max(
      1,
      ...adminAnalytics.weekdays.map((item) => item.count)
    )

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

            </div>

          </section>


          {/* SAFETY DECISIONS */}

          <section className='analytics-card'>

            <h2>Safety Decisions</h2>

            <p className='analytics-intro'>
              Results from safety screening across all users.
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
            </p>


            <div className='tool-usage-list'>

              {adminAnalytics.copingTools.map((tool) => (

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

              {adminAnalytics.architectureHealth.map((layer) => (

                <div
                  className='admin-health-item'
                  key={layer.name}
                >

                  <span>
                    {layer.name}
                  </span>

                  <strong>
                    {layer.status}
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

              {adminAnalytics.recentLogs.map((log, index) => (

                <div
                  className={`admin-log-item ${log.status === 'Warning'
                      ? 'is-warning'
                      : log.status === 'Error'
                        ? 'is-error'
                        : ''
                    }`}
                  key={index}
                >

                  <div>

                    <span>
                      {log.time} · {log.type}
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

          {/* CONVERSATION HEADER */}
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

            {/* NON-CLINICAL SUPPORT NOTICE */}
            <div className='conversation-notice'>
              <strong>Previous Conversation</strong>

              <p>
                You are viewing a previous conversation session. New messages
                will continue to follow the same safety and non-clinical
                support controls.
              </p>
            </div>


            {/* MESSAGE AREA */}
            <div className='message-area'>

              {/* BACKEND INTEGRATION:
                Replace this placeholder with the actual messages
                returned for selectedSession from the backend.
                
                Example:
                GET /sessions/{session_id}
            */}

              <div className='message assistant-message'>
                <span className='message-label'>
                  AI Companion
                </span>

                <p>
                  Welcome back. Let's continue reflecting on this conversation.
                </p>
              </div>


              {/* DISPLAY NEW MESSAGES */}
              {continueMessages.map((item, index) => (
                <div
                  key={index}
                  className={
                    item.role === 'user'
                      ? 'message user-message'
                      : 'message assistant-message'
                  }
                >

                  <span className='message-label'>
                    {item.role === 'user'
                      ? 'You'
                      : 'AI Companion'}
                  </span>

                  <p>
                    {item.text}
                  </p>

                </div>
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

            </div>


            {/* MESSAGE FORM */}

            {/* BACKEND INTEGRATION:
              This form will eventually use the same
              safety → AI → save-message workflow as the
              main Conversation screen.
          */}

            <form
              className='message-form'
              onSubmit={(event) => {
                event.preventDefault()

                // Do not submit empty messages
                // Do not submit while safety check is running
                if (
                  !continueMessage.trim() ||
                  continueSafetyChecking
                ) {
                  return
                }

                const userMessage = continueMessage.trim()


                // ============================================================
                // ADD USER MESSAGE
                // ============================================================

                setContinueMessages((currentMessages) => [
                  ...currentMessages,
                  {
                    role: 'user',
                    text: userMessage
                  }
                ])


                // Clear input
                setContinueMessage('')


                // ============================================================
                // START SAFETY CHECK
                // ============================================================

                setContinueSafetyChecking(true)


                // ============================================================
                // SAFETY BACKEND INTEGRATION:
                //
                // Replace this setTimeout prototype with a request
                // to the FastAPI backend.
                //
                // Intended flow:
                //
                // React
                //   ↓
                // FastAPI
                //   ↓
                // Safety / Moderation Service
                //   ↓
                // clear / concern / error
                //
                // ============================================================

                setTimeout(() => {

                  // ----------------------------------------------------------
                  // TEMPORARY PROTOTYPE RESULT
                  // ----------------------------------------------------------
                  // Change this to:
                  //
                  // 'clear'   → continue to AI response
                  // 'concern' → go to support resources
                  // 'error'   → go to safety error
                  //
                  // BACKEND INTEGRATION:
                  // Replace this hard-coded value with the actual
                  // safety API response.
                  // ----------------------------------------------------------

                  const safetyResult = 'clear'


                  // Stop safety checking
                  setContinueSafetyChecking(false)


                  // ============================================================
                  // SAFETY CONCERN
                  // ============================================================

                  if (safetyResult === 'concern') {
                    setCurrentScreen('support-resources')
                    return
                  }


                  // ============================================================
                  // SAFETY SERVICE ERROR
                  // ============================================================

                  if (safetyResult === 'error') {
                    setCurrentScreen('safety-error')
                    return
                  }


                  // ============================================================
                  // AI BACKEND INTEGRATION
                  // ============================================================
                  //
                  // The message has passed the safety check.
                  //
                  // Replace the mock response below with the response
                  // returned by the conversational AI through FastAPI.
                  //
                  // Intended flow:
                  //
                  // Safety-approved message
                  //        ↓
                  // FastAPI
                  //        ↓
                  // Conversational AI
                  //        ↓
                  // AI response
                  //        ↓
                  // React
                  //
                  // ============================================================

                  setContinueMessages((currentMessages) => [
                    ...currentMessages,
                    {
                      role: 'assistant',
                      text: 'Is there something that happened today to make you feel like that?'
                    }
                  ])


                  // ============================================================
                  // DATABASE BACKEND INTEGRATION
                  // ============================================================
                  //
                  // Save the user message and AI response to the
                  // selected conversation session.
                  //
                  // Example future endpoint:
                  //
                  // POST /sessions/{session_id}/messages
                  //
                  // The backend should also record appropriate
                  // safety/event metadata for analytics.
                  //
                  // Raw conversation content should not be exposed
                  // in aggregate analytics.
                  //
                  // ============================================================

                }, 1000)
              }}
            >


              {/* MESSAGE INPUT */}

              <label
                htmlFor='continue-message'
                className='sr-only'
              >
                Message
              </label>

              <input
                id='continue-message'
                type='text'
                placeholder="What's on your mind today?"
                value={continueMessage}
                onChange={(event) =>
                  setContinueMessage(event.target.value)
                }
                disabled={continueSafetyChecking}
              />


              {/* SEND BUTTON */}

              <button
                type='submit'
                disabled={continueSafetyChecking}
              >
                {continueSafetyChecking
                  ? 'Checking...'
                  : 'Send'}
              </button>

            </form>


            {/* SAFETY FOOTER */}

            <p className='conversation-footer'>
              Your messages will be screened for potential safety concerns
              before a response is generated.
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

            {/* END SESSION */}
            <div className='support-actions'>
              <button className='secondary-button'
                type='button'
                onClick={() => {
                  setMessages([])
                  setCurrentScreen('home')
                }}>End Session
              </button>
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

            <p className='support-description'>You can try again, uuse a coping tool or end the session.</p>

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
                onClick={() => setCurrentScreen('conversation')}
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
                onClick={() => {
                  setMessages([])
                  setCurrentScreen('home')
                }}
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
