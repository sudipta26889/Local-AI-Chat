import React, { useEffect, useState } from 'react';
import { Link, useParams, useNavigate } from 'react-router-dom';
import { format } from 'date-fns';
import { PlusIcon, ChatBubbleLeftRightIcon, TrashIcon, PencilIcon, CheckIcon, XMarkIcon } from '@heroicons/react/24/outline';
import { Chat } from '../../types';
import api from '../../services/api';
import toast from 'react-hot-toast';

interface ChatListProps {
  onNewChat: () => void;
}

export const ChatList: React.FC<ChatListProps> = ({ onNewChat }) => {
  const { chatId } = useParams<{ chatId: string }>();
  const navigate = useNavigate();
  const [chats, setChats] = useState<Chat[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [editingChatId, setEditingChatId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState('');

  const fetchChats = async () => {
    try {
      const data = await api.getChats();
      setChats(data);
    } catch (error) {
      toast.error('Failed to load chats');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchChats();
  }, []);

  const handleDeleteChat = async (id: string, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();

    if (!window.confirm('Are you sure you want to delete this chat?')) {
      return;
    }

    try {
      await api.deleteChat(id);
      setChats(chats.filter((chat) => chat.id !== id));
      
      // If the deleted chat is the currently active one, redirect to homepage
      if (chatId === id) {
        navigate('/');
      }
      
      toast.success('Chat deleted');
    } catch (error) {
      toast.error('Failed to delete chat');
    }
  };

  const handleEditClick = (chat: Chat, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setEditingChatId(chat.id);
    setEditingTitle(chat.title);
  };

  const handleSaveEdit = async (chatId: string) => {
    if (!editingTitle.trim()) {
      toast.error('Chat title cannot be empty');
      return;
    }

    try {
      const updatedChat = await api.updateChat(chatId, { title: editingTitle.trim() });
      setChats(chats.map(chat => chat.id === chatId ? updatedChat : chat));
      setEditingChatId(null);
      toast.success('Chat renamed');
    } catch (error) {
      toast.error('Failed to rename chat');
    }
  };

  const handleCancelEdit = () => {
    setEditingChatId(null);
    setEditingTitle('');
  };

  const handleKeyDown = (e: React.KeyboardEvent, chatId: string) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleSaveEdit(chatId);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      handleCancelEdit();
    }
  };

  return (
    <div className="w-64 bg-gray-900 text-white h-full overflow-y-auto">
      <div className="p-4">
        <button
          onClick={onNewChat}
          className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-primary-600 hover:bg-primary-700 rounded-lg transition-colors"
        >
          <PlusIcon className="h-5 w-5" />
          New Chat
        </button>
      </div>

      <div className="px-2">
        <h3 className="px-2 text-xs font-semibold text-gray-400 uppercase tracking-wider">
          Recent Chats
        </h3>
        
        {isLoading ? (
          <div className="p-4 text-center text-gray-400">
            Loading chats...
          </div>
        ) : chats.length === 0 ? (
          <div className="p-4 text-center text-gray-400">
            No chats yet. Start a new conversation!
          </div>
        ) : (
          <ul className="mt-2 space-y-1">
            {chats.map((chat) => (
              <li key={chat.id}>
                <Link
                  to={`/chat/${chat.id}`}
                  className={`group flex items-center justify-between px-2 py-2 text-sm rounded-lg hover:bg-gray-800 transition-colors ${
                    chatId === chat.id ? 'bg-gray-800' : ''
                  }`}
                >
                  <div className="flex items-center gap-2 min-w-0 flex-1">
                    <ChatBubbleLeftRightIcon className="h-4 w-4 flex-shrink-0 text-gray-400" />
                    <div className="min-w-0 flex-1">
                      {editingChatId === chat.id ? (
                        <div className="flex items-center gap-1">
                          <input
                            type="text"
                            value={editingTitle}
                            onChange={(e) => setEditingTitle(e.target.value)}
                            onKeyDown={(e) => handleKeyDown(e, chat.id)}
                            className="flex-1 px-1 py-0.5 text-sm bg-gray-700 border border-gray-600 rounded focus:border-primary-500 focus:outline-none"
                            autoFocus
                          />
                          <button
                            onClick={() => handleSaveEdit(chat.id)}
                            className="p-0.5 hover:bg-gray-700 rounded"
                          >
                            <CheckIcon className="h-3 w-3 text-green-400" />
                          </button>
                          <button
                            onClick={handleCancelEdit}
                            className="p-0.5 hover:bg-gray-700 rounded"
                          >
                            <XMarkIcon className="h-3 w-3 text-red-400" />
                          </button>
                        </div>
                      ) : (
                        <>
                          <p className="truncate font-medium">{chat.title}</p>
                          <p className="text-xs text-gray-400">
                            {format(new Date(chat.updated_at), 'MMM d, h:mm a')}
                          </p>
                        </>
                      )}
                    </div>
                  </div>
                  {editingChatId !== chat.id && (
                    <div className="flex items-center opacity-0 group-hover:opacity-100 transition-opacity">
                      <button
                        onClick={(e) => handleEditClick(chat, e)}
                        className="p-1 hover:bg-gray-700 rounded"
                      >
                        <PencilIcon className="h-4 w-4 text-gray-400 hover:text-primary-400" />
                      </button>
                      <button
                        onClick={(e) => handleDeleteChat(chat.id, e)}
                        className="p-1 hover:bg-gray-700 rounded"
                      >
                        <TrashIcon className="h-4 w-4 text-gray-400 hover:text-red-400" />
                      </button>
                    </div>
                  )}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
};