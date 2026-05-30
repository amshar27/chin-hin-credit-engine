import { useState, useRef, useEffect } from 'react'
import { Send, Bot, User, Loader2, Sparkles, AlertTriangle, Minus } from 'lucide-react'
import './DataCopilot.css'

function DataCopilot({ currentData, onDataUpdated, onMinimize }) {
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      text: 'Hello! I\'m your AI Data Copilot. Ask me questions about the form data or request changes — I can help with both.',
    },
  ])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const chatAreaRef = useRef(null)
  const inputRef = useRef(null)

  // Scroll chat to bottom — uses scrollTop on the container itself,
  // NOT scrollIntoView which propagates to ancestor scrollable elements.
  useEffect(() => {
    const el = chatAreaRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages, isLoading])

  const handleSend = async () => {
    const prompt = input.trim()
    if (!prompt || isLoading) return

    setInput('')
    setMessages(prev => [...prev, { role: 'user', text: prompt }])
    setIsLoading(true)

    try {
      const res = await fetch('http://localhost:8000/api/refine-data', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          current_data: currentData,
          user_prompt: prompt,
        }),
      })

      if (!res.ok) {
        const errBody = await res.json().catch(() => null)
        throw new Error(errBody?.detail || `Server error (${res.status})`)
      }

      const { updated_data, message } = await res.json()
      const hasChanged = JSON.stringify(updated_data) !== JSON.stringify(currentData)

      if (hasChanged) {
        onDataUpdated(updated_data)
      }

      setMessages(prev => [
        ...prev,
        {
          role: 'assistant',
          text: message || (hasChanged ? 'Done — form data has been updated.' : 'No changes were needed.'),
          isSuccess: hasChanged,
        },
      ])
    } catch (err) {
      setMessages(prev => [
        ...prev,
        {
          role: 'assistant',
          text: `Sorry, I wasn't able to process that. ${err.message || 'Please try again.'}`,
          isError: true,
        },
      ])
    } finally {
      setIsLoading(false)
      inputRef.current?.focus({ preventScroll: true })
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="copilot-sidebar-inner">
      <div className="copilot-header">
        <Sparkles size={15} className="copilot-header-icon" />
        <span className="copilot-title">AI Data</span>
        <button
          type="button"
          className="copilot-header-btn"
          onClick={(e) => { e.preventDefault(); e.stopPropagation(); onMinimize(); }}
          title="Minimize"
        >
          <Minus size={15} />
        </button>
      </div>

      <div className="copilot-chat-area" ref={chatAreaRef}>
        {messages.map((msg, i) => (
          <div key={i} className={`copilot-msg copilot-msg--${msg.role}`}>
            <div className="copilot-msg-avatar">
              {msg.role === 'assistant' ? <Bot size={13} /> : <User size={13} />}
            </div>
            <div
              className={`copilot-msg-bubble${
                msg.isError ? ' copilot-msg-bubble--error' : ''
              }${msg.isSuccess ? ' copilot-msg-bubble--success' : ''}`}
            >
              {msg.isError && <AlertTriangle size={12} className="copilot-msg-err-icon" />}
              {msg.text}
            </div>
          </div>
        ))}

        {isLoading && (
          <div className="copilot-msg copilot-msg--assistant">
            <div className="copilot-msg-avatar"><Bot size={13} /></div>
            <div className="copilot-msg-bubble copilot-msg-bubble--loading">
              <Loader2 size={13} className="spin" />
              <span>Thinking...</span>
            </div>
          </div>
        )}
      </div>

      <div className="copilot-input-area">
        <textarea
          ref={inputRef}
          className="copilot-input"
          rows={2}
          placeholder="Ask a question or request a change..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={isLoading}
        />
        <button
          type="button"
          className="copilot-send-btn"
          onClick={handleSend}
          disabled={!input.trim() || isLoading}
          title="Send"
        >
          <Send size={15} />
        </button>
      </div>
    </div>
  )
}

export default DataCopilot
