import React, { useState, useEffect, useRef } from 'react';
import { MessageSquare, Activity, Database, FileText, Send, Trash2, Zap, BrainCircuit, Clock, Book, UserCheck, LogOut } from 'lucide-react';
import './App.css';
import Login from './Login';

function App() {
  const [token, setToken] = useState(localStorage.getItem('token'));
  const [username, setUsername] = useState(localStorage.getItem('username'));
  const [messages, setMessages] = useState([]);
  const [inputText, setInputText] = useState('');
  const [timeline, setTimeline] = useState([]);
  const [memories, setMemories] = useState([]);
  const [currentPrompt, setCurrentPrompt] = useState(null);
  const [loading, setLoading] = useState(false);
  const [socket, setSocket] = useState(null);
const [activeTab, setActiveTab] = useState('ALL');

  const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8001';
  const WS_BASE = import.meta.env.VITE_WS_URL || 'ws://localhost:8001';

  const timelineEndRef = useRef(null);
  const chatEndRef = useRef(null);

  useEffect(() => {
    if (!token) return;

    let ws;
    let isMounted = true;

    const connect = () => {
      // Pass token in query string for WebSocket auth
      ws = new WebSocket(`${WS_BASE}/ws/events?token=${token}`);

      ws.onopen = () => {
        if (isMounted) console.log('WebSocket connected');
      };

      ws.onmessage = (event) => {
        if (!isMounted) return;
        const { type, data } = JSON.parse(event.data);
        handleWsEvent(type, data);
      };

      ws.onclose = (e) => {
        if (isMounted && token) {
          console.log('WebSocket disconnected, retrying in 2s...', e.reason);
          setTimeout(connect, 2000);
        }
      };

      ws.onerror = (err) => {
        console.error('WebSocket error:', err);
        ws.close();
      };

      setSocket(ws);
    };

    connect();
    fetchMemories();

    return () => {
      isMounted = false;
      if (ws) ws.close();
    };
  }, [token]);

  useEffect(() => {
    timelineEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [timeline]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleLogin = (newToken, newUsername) => {
    localStorage.setItem('token', newToken);
    localStorage.setItem('username', newUsername);
    setToken(newToken);
    setUsername(newUsername);
    setTimeline([]);
    setMessages([]);
    setCurrentPrompt(null);
  };

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('username');
    setToken(null);
    setUsername(null);
    if (socket) socket.close();
  };

  const fetchMemories = async () => {
    if (!token) return;
    try {
      const res = await fetch(`${API_BASE}/memories`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.status === 401) return handleLogout();
      const data = await res.json();
      setMemories(Array.isArray(data) ? data : []);
    } catch (e) {
      console.error("Failed to fetch memories", e);
      setMemories([]);
    }
  };

  const handleWsEvent = (type, data) => {
    const timestamp = new Date().toLocaleTimeString();

    switch (type) {
      case 'USER_MESSAGE':
        setTimeline(prev => [...prev, { type: 'user', label: 'User Message', content: data.message, time: timestamp }]);
        break;
      case 'PIPELINE_STEP':
        setTimeline(prev => [...prev, { type: 'step', label: 'Pipeline', content: data.step, time: timestamp }]);
        break;
      case 'MEMORY_EXTRACTED':
        setTimeline(prev => [...prev, { type: 'memory', label: 'Memory Extracted', content: data.facts.length > 0 ? data.facts.join(', ') : 'No new facts', time: timestamp }]);
        break;
      case 'MEMORY_STORED':
        setTimeline(prev => [...prev, { type: 'memory', label: 'Memory Stored', content: `${data.memories.length} item(s) saved to SQLite`, time: timestamp }]);
        fetchMemories();
        break;
      case 'MEMORY_RETRIEVED':
        setTimeline(prev => [...prev, { type: 'memory', label: 'Memory Retrieved', content: `${data.memories.length} relevant context(s) found across layers`, time: timestamp }]);
        break;
      case 'PROMPT_CREATED':
        setTimeline(prev => [...prev, { type: 'step', label: 'Prompt Created', content: 'Multi-layer context injected', time: timestamp }]);
        setCurrentPrompt(data);
        break;
      case 'LLM_RESPONSE':
        setTimeline(prev => [...prev, { type: 'llm', label: 'Assistant Response', content: 'Response generated', time: timestamp }]);
        setMessages(prev => [...prev, { role: 'assistant', content: data.response }]);
        setLoading(false);
        break;
      case 'ERROR':
        setTimeline(prev => [...prev, { type: 'error', label: 'Error', content: data.message, time: timestamp }]);
        setLoading(false);
        break;
      default:
        break;
    }
  };

  const sendMessage = async () => {
    if (!inputText.trim() || loading || !token) return;

    const msg = inputText;
    setInputText('');
    setLoading(true);
    setMessages(prev => [...prev, { role: 'user', content: msg }]);

    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ message: msg })
      });
      if (res.status === 401) return handleLogout();
      if (!res.ok) setLoading(false);
    } catch (e) {
      console.error("Failed to send message", e);
      setLoading(false);
    }
  };

  const clearMemory = async () => {
    if (!confirm("Clear all long-term memories?")) return;
    try {
      const res = await fetch(`${API_BASE}/memories`, { 
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.status === 401) return handleLogout();
      setMemories([]);
      setTimeline(prev => [...prev, { type: 'step', label: 'System', content: 'Memories cleared from SQLite', time: new Date().toLocaleTimeString() }]);
    } catch (e) {
      console.error("Failed to clear memories", e);
    }
  };

  if (!token) {
    return <Login onLogin={handleLogin} />;
  }

  const filteredMemories = Array.isArray(memories)
    ? memories.filter(m => activeTab === 'ALL' || m.type === activeTab)
    : [];

  const getMemoryIcon = (type) => {
    switch (type) {
      case 'FACTUAL': return <UserCheck size={14} />;
      case 'EPISODIC': return <Clock size={14} />;
      case 'SEMANTIC': return <Book size={14} />;
      default: return <Database size={14} />;
    }
  };

  return (
    <div className="app-container">
      {/* LEFT: CHAT */}
      <div className="panel chat-panel">
        <div className="panel-header">
          <h2><MessageSquare size={18} /> Chat Conversation</h2>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-dim)' }}>{username}</span>
            <button className="logout-btn" onClick={handleLogout}>
              <LogOut size={14} /> Logout
            </button>
          </div>
        </div>
        <div className="panel-content">
          <div className="chat-messages">
            {messages.length === 0 && (
              <div style={{ color: 'var(--text-dim)', textAlign: 'center', marginTop: '50px', fontSize: '0.9rem' }}>
                👋 Welcome back, <strong>{username}</strong>!<br />
                Try saying:<br />
                <em>"I'm a senior dev living in Tokyo"</em> or<br />
                <em>"I remember eating a great sushi last night"</em>
              </div>
            )}
            {messages.map((m, i) => (
              <div key={i} className={`message ${m.role}`}>
                {m.content}
              </div>
            ))}
            {loading && <div className="message assistant">...</div>}
            <div ref={chatEndRef} />
          </div>
        </div>
        <div className="chat-input">
          <input
            type="text"
            placeholder="Type a message..."
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            onKeyPress={(e) => e.key === 'Enter' && sendMessage()}
          />
          <button onClick={sendMessage} disabled={loading}>
            <Send size={18} />
          </button>
        </div>
      </div>

      {/* CENTER: TIMELINE */}
      <div className="panel timeline-panel">
        <div className="panel-header">
          <h2><Activity size={18} /> Memory Pipeline</h2>
          <button onClick={() => setTimeline([])} style={{ background: 'none', border: 'none', color: 'var(--text-dim)', cursor: 'pointer' }}>
            <Trash2 size={16} />
          </button>
        </div>
        <div className="panel-content">
          <div className="timeline">
            {timeline.length === 0 && <div style={{ color: 'var(--text-dim)', textAlign: 'center', marginTop: '20px' }}>Internal events will stream here</div>}
            {timeline.map((item, i) => (
              <div key={i} className={`timeline-item ${item.type}`}>
                <div className="timeline-label">{item.label} <span style={{ fontSize: '0.65rem', float: 'right' }}>{item.time}</span></div>
                <div className="timeline-content">{item.content}</div>
              </div>
            ))}
            <div ref={timelineEndRef} />
          </div>
        </div>
      </div>

      {/* RIGHT: STORAGE & PROMPT */}
      <div className="panel storage-panel">
        <div className="panel-header">
          <h2><BrainCircuit size={18} /> 4-Layer Memory</h2>
          <button onClick={clearMemory} style={{ background: 'none', border: 'none', color: 'var(--text-dim)', cursor: 'pointer' }}>
            <Zap size={16} />
          </button>
        </div>
        <div className="panel-content">
          <div className="inspector-section">
            <div className="inspector-label"><FileText size={14} style={{ verticalAlign: 'middle', marginRight: '4px' }} /> Prompt Inspector</div>
            {currentPrompt ? (
              <div className="code-block" style={{ maxHeight: '200px', overflowY: 'auto' }}>
                <strong>SYSTEM:</strong><br />
                {currentPrompt.system_prompt}<br /><br />
                <strong>USER:</strong><br />
                {currentPrompt.user_message}
              </div>
            ) : (
              <div style={{ color: 'var(--text-dim)', fontSize: '0.8rem' }}>Dynamic prompt context shown here</div>
            )}
          </div>

          <div className="memory-tabs">
            {['ALL', 'FACTUAL', 'EPISODIC', 'SEMANTIC'].map(tab => (
              <button
                key={tab}
                className={`tab-btn ${activeTab === tab ? 'active' : ''}`}
                onClick={() => setActiveTab(tab)}
              >
                {tab}
              </button>
            ))}
          </div>

          <div style={{ marginTop: '15px' }}>
            {filteredMemories.length === 0 && <div style={{ color: 'var(--text-dim)', fontSize: '0.8rem', textAlign: 'center' }}>No {activeTab.toLowerCase()} memories found</div>}
            {filteredMemories.map((m, i) => (
              <div key={i} className={`memory-card type-${m.type}`}>
                <div className="memory-header">
                  <span className="memory-icon">{getMemoryIcon(m.type)}</span>
                  <span className="memory-type-label">{m.type}</span>
                </div>
                <div className="memory-text">{m.memory}</div>
                <div className="memory-meta">{new Date(m.created_at).toLocaleDateString()} at {new Date(m.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;
