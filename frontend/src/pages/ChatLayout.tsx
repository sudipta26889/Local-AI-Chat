import React, { useState } from 'react';
import { Routes, Route, useNavigate } from 'react-router-dom';
import { Header } from '../components/common/Header';
import { ChatList } from '../components/chat/ChatList';
import { ChatWindow } from '../components/chat/ChatWindow';
import api from '../services/api';
import toast from 'react-hot-toast';

export const ChatLayout: React.FC = () => {
  const navigate = useNavigate();

  const handleNewChat = async () => {
    try {
      // Fetch models to get the default model
      const modelsResponse = await api.getModels();
      const defaultModel = modelsResponse.default_model;
      
      // Create chat with default model preferences
      const newChat = await api.createChat('New Chat', undefined, {
        default_model: defaultModel
      });
      
      navigate(`/chat/${newChat.id}`);
      toast.success('New chat created');
    } catch (error) {
      console.error('Failed to create new chat:', error);
      toast.error('Failed to create new chat');
    }
  };

  return (
    <div className="h-screen flex flex-col">
      <Header />
      
      <div className="flex-1 flex overflow-hidden">
        <ChatList onNewChat={handleNewChat} />
        
        <Routes>
          <Route path="/" element={<ChatWindow />} />
          <Route path="/chat/:chatId" element={<ChatWindow />} />
        </Routes>
      </div>
    </div>
  );
};