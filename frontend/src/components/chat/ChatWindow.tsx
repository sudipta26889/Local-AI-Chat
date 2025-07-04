import React, { useEffect, useState, useRef } from 'react';
import { useParams } from 'react-router-dom';
import { Chat, Message, WebSocketMessage } from '../../types';
import { MessageList } from './MessageList';
import { MessageInput } from './MessageInput';
import { ModelSelector } from './ModelSelector';
import { ChatWebSocket } from '../../services/websocket';
import api from '../../services/api';
import toast from 'react-hot-toast';

export const ChatWindow: React.FC = () => {
  const { chatId } = useParams<{ chatId: string }>();
  const [chat, setChat] = useState<Chat | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isStreaming, setIsStreaming] = useState(false);
  const [selectedModel, setSelectedModel] = useState<string>('');
  const [temperature, setTemperature] = useState(0.7);
  const wsRef = useRef<ChatWebSocket | null>(null);
  const streamingMessageRef = useRef<string>('');

  useEffect(() => {
    if (chatId) {
      loadChat();
      loadMessages();
      connectWebSocket();
    }

    return () => {
      wsRef.current?.disconnect();
    };
  }, [chatId]);

  const loadChat = async () => {
    if (!chatId) return;
    
    try {
      const data = await api.getChat(chatId);
      setChat(data);
      setSelectedModel(data.model_preferences.default_model || '');
    } catch (error) {
      toast.error('Failed to load chat');
    }
  };

  const loadMessages = async () => {
    if (!chatId) return;
    
    setIsLoading(true);
    try {
      const data = await api.getChatMessages(chatId);
      setMessages(data);
    } catch (error) {
      toast.error('Failed to load messages');
    } finally {
      setIsLoading(false);
    }
  };

  const connectWebSocket = () => {
    if (!chatId) return;

    const wsUrl = api.getWebSocketUrl(chatId);
    
    wsRef.current = new ChatWebSocket(
      wsUrl,
      handleWebSocketMessage,
      (error) => {
        console.error('WebSocket error:', error);
        toast.error(error);
        
        // If streaming was in progress, mark it as interrupted
        if (isStreaming) {
          setIsStreaming(false);
          toast('Connection lost during response. Attempting to reconnect...', { icon: '⚠️' });
        }
      },
      () => {
        console.log('WebSocket connected');
        // If we reconnected while streaming, warn user
        if (isStreaming) {
          toast.success('Connection restored');
        }
      },
      () => {
        console.log('WebSocket disconnected');
        // Reset streaming state on disconnect
        if (isStreaming) {
          setIsStreaming(false);
        }
      }
    );

    wsRef.current.connect();
  };

  const handleWebSocketMessage = (message: WebSocketMessage) => {
    switch (message.type) {
      case 'user_message':
        if (message.message_id && message.content && message.created_at) {
          const userMessage: Message = {
            id: message.message_id,
            chat_id: chatId!,
            role: 'user',
            content: message.content,
            created_at: message.created_at,
          };
          setMessages((prev) => [...prev, userMessage]);
        }
        break;

      case 'stream_start':
        setIsStreaming(true);
        streamingMessageRef.current = '';
        if (message.message_id) {
          const assistantMessage: Message = {
            id: message.message_id,
            chat_id: chatId!,
            role: 'assistant',
            content: '',
            created_at: new Date().toISOString(),
            model_used: selectedModel,
          };
          setMessages((prev) => [...prev, assistantMessage]);
        }
        break;

      case 'stream_chunk':
        if (message.content && message.message_id) {
          streamingMessageRef.current += message.content;
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === message.message_id
                ? { ...msg, content: streamingMessageRef.current }
                : msg
            )
          );
          
          // Debug logging to track content building
          if (streamingMessageRef.current.length % 100 === 0) {
            console.log(`Streaming progress: ${streamingMessageRef.current.length} characters received`);
          }
        }
        break;

      case 'stream_end':
        setIsStreaming(false);
        if (message.message_id) {
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === message.message_id
                ? { 
                    ...msg, 
                    tokens_used: message.tokens_used,
                    // Use complete response from stream_end as backup if provided
                    content: message.content || msg.content || streamingMessageRef.current
                  }
                : msg
            )
          );
        }
        break;

      case 'stream_complete':
        // Fallback handler - ensure we have the complete response
        console.log('Received stream_complete, ensuring full content is displayed');
        if (message.message_id && message.full_content) {
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === message.message_id
                ? { ...msg, content: message.full_content || msg.content }
                : msg
            )
          );
        }
        break;

      case 'stream_error':
        setIsStreaming(false);
        console.error('Streaming error:', message.error);
        toast.error(message.error || 'Streaming error occurred');
        
        // Keep partial response if any content was received
        if (message.message_id && streamingMessageRef.current) {
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === message.message_id
                ? { ...msg, content: streamingMessageRef.current + ' [Response was cut short due to connection issues]' }
                : msg
            )
          );
        } else if (message.message_id) {
          // Remove the failed message only if no content was received
          setMessages((prev) => prev.filter((msg) => msg.id !== message.message_id));
        }
        break;

      case 'error':
        toast.error(message.error || 'An error occurred');
        break;
    }
  };

  const handleSendMessage = (content: string) => {
    if (!wsRef.current?.isConnected()) {
      toast.error('Not connected to chat server');
      return;
    }

    if (!selectedModel) {
      toast.error('Please select a model before sending a message');
      return;
    }

    wsRef.current.sendMessage(content, selectedModel, temperature);
  };

  const handleModelChange = async (model: string) => {
    setSelectedModel(model);
    
    if (chat && chatId) {
      try {
        await api.updateChat(chatId, {
          model_preferences: { ...chat.model_preferences, default_model: model },
        });
      } catch (error) {
        console.error('Failed to update model preference:', error);
      }
    }
  };

  if (!chatId) {
    return (
      <div className="flex-1 flex items-center justify-center bg-gray-50">
        <div className="text-center">
          <div className="flex justify-center mb-6">
            <img 
              src="/logo.png" 
              alt="Dharas Local AI" 
              className="h-24 w-24 rounded-3xl shadow-xl"
            />
          </div>
          <h2 className="text-2xl font-semibold text-gray-900">Welcome to DharasLocalAI</h2>
          <p className="mt-2 text-gray-600">Your personal AI assistant with advanced features</p>
          <p className="mt-1 text-sm text-gray-500">Select a chat or create a new one to get started</p>
        </div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center bg-gray-50">
        <div className="text-center">
          <div className="flex justify-center mb-4">
            <img 
              src="/logo.png" 
              alt="Dharas Local AI" 
              className="h-16 w-16 rounded-2xl animate-pulse"
            />
          </div>
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Loading chat...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col bg-gray-50">
      <div className="border-b border-gray-200 bg-white px-6 py-4">
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-semibold text-gray-900">{chat?.title || 'Chat'}</h1>
          <div className="flex items-center gap-4">
            <ModelSelector
              selectedModel={selectedModel}
              onModelChange={handleModelChange}
            />
            <div className="flex items-center gap-2">
              <label htmlFor="temperature" className="text-sm text-gray-600">
                Temperature:
              </label>
              <input
                id="temperature"
                type="range"
                min="0"
                max="1"
                step="0.1"
                value={temperature}
                onChange={(e) => setTemperature(parseFloat(e.target.value))}
                className="w-24"
              />
              <span className="text-sm text-gray-600 w-8">{temperature}</span>
            </div>
          </div>
        </div>
      </div>

      <MessageList messages={messages} isStreaming={isStreaming} />

      <MessageInput
        onSendMessage={handleSendMessage}
        disabled={isStreaming || !wsRef.current?.isConnected()}
      />
    </div>
  );
};