import React, { useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import remarkGfm from 'remark-gfm';
import { format } from 'date-fns';
import { UserIcon, CpuChipIcon } from '@heroicons/react/24/outline';
import { Message } from '../../types';
import { useAuthStore } from '../../services/auth';

interface MessageListProps {
  messages: Message[];
  isStreaming: boolean;
}

export const MessageList: React.FC<MessageListProps> = ({ messages, isStreaming }) => {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const { user } = useAuthStore();

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const renderMessage = (message: Message) => {
    const isUser = message.role === 'user';
    const isLastMessage = messages[messages.length - 1]?.id === message.id;
    const isStreamingMessage = isLastMessage && isStreaming && !isUser;

    return (
      <div
        key={message.id}
        className={`flex gap-4 p-6 ${isUser ? 'bg-white' : 'bg-gray-50'}`}
      >
        <div className="flex-shrink-0">
          {isUser ? (
            <div className="w-8 h-8 bg-primary-600 rounded-full flex items-center justify-center">
              <UserIcon className="h-5 w-5 text-white" />
            </div>
          ) : (
            <div className="w-8 h-8 bg-gray-700 rounded-full flex items-center justify-center">
              <CpuChipIcon className="h-5 w-5 text-white" />
            </div>
          )}
        </div>
        
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="font-medium text-gray-900">
              {isUser ? user?.display_name || 'You' : 'Assistant'}
            </span>
            <span className="text-xs text-gray-500">
              {format(new Date(message.created_at), 'h:mm a')}
            </span>
            {message.model_used && (
              <span className="text-xs text-gray-500 bg-gray-200 px-2 py-0.5 rounded">
                {message.model_used}
              </span>
            )}
            {message.tokens_used && (
              <span className="text-xs text-gray-500">
                {message.tokens_used} tokens
              </span>
            )}
          </div>
          
          <div className="prose prose-sm max-w-none">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                code({ node, inline, className, children, ...props }: any) {
                  const match = /language-(\w+)/.exec(className || '');
                  return !inline && match ? (
                    <SyntaxHighlighter
                      style={oneDark as any}
                      language={match[1]}
                      PreTag="div"
                      {...props}
                    >
                      {String(children).replace(/\n$/, '')}
                    </SyntaxHighlighter>
                  ) : (
                    <code className={className} {...props}>
                      {children}
                    </code>
                  );
                },
              }}
            >
              {message.content || (isStreamingMessage ? '...' : '')}
            </ReactMarkdown>
            
            {isStreamingMessage && (
              <span className="inline-block w-2 h-4 bg-gray-900 animate-pulse ml-1" />
            )}
          </div>
          
          {message.attachments && message.attachments.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-2">
              {message.attachments.map((attachment) => (
                <div
                  key={attachment.id}
                  className="flex items-center gap-2 px-3 py-1 bg-gray-100 rounded-lg text-sm"
                >
                  <span>{attachment.file_name}</span>
                  <span className="text-xs text-gray-500">
                    ({Math.round((attachment.file_size || 0) / 1024)} KB)
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="flex-1 overflow-y-auto scrollbar-thin">
      {messages.length === 0 ? (
        <div className="h-full flex items-center justify-center">
          <div className="text-center text-gray-500">
            <CpuChipIcon className="h-12 w-12 mx-auto mb-4 text-gray-400" />
            <p>No messages yet. Start a conversation!</p>
          </div>
        </div>
      ) : (
        <>
          {messages.map(renderMessage)}
          <div ref={messagesEndRef} />
        </>
      )}
    </div>
  );
};