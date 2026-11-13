/*
  FRONTEND SERVICE

  This file simulates the response from our future FastAPI backend.
  Later, we will replace this mock function with a real API request.

  The backend will be responsible for safety screening,
  scope classification, and generating wellness responses.
*/

export async function sendMessageToBackend(userMessage) {
  // MOCK ONLY: Simulate a short backend response delay.
  await new Promise((resolve) => setTimeout(resolve, 500))

  const text = userMessage.toLowerCase()

  // MOCK TEST: A direct recipe request is out of scope.
  if (
    text.includes('recipe') ||
    text.includes('how do i cook')
  ) {
    return {
      status: 'out_of_scope',
      message:
        "I'm here to support emotional wellness, self-reflection, and coping strategies. I can't help with recipes, but we could explore how you're feeling."
    }
  }

  // MOCK TEST: An emotional message mentioning food stays in scope.
  if (
    text.includes('stressed') ||
    text.includes('stress') ||
    text.includes('upset') ||
    text.includes('sad')
  ) {
    return {
      status: 'ok',
      message:
        "It sounds like you're feeling stressed. Would you like to talk about what's making today difficult?"
    }
  }

  // MOCK DEFAULT: Replace this with the real AI response.
  return {
    status: 'ok',
    message:
      'What has been on your mind today?'
  }
}