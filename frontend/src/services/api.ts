import axios, { AxiosInstance } from 'axios';
import { AuthResponse, Chat, LoginCredentials, Message, Model, ModelsResponse, User } from '../types';

const API_BASE_URL = process.env.REACT_APP_API_URL || '/api';

class ApiService {
  private api: AxiosInstance;

  constructor() {
    this.api = axios.create({
      baseURL: API_BASE_URL,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    // Request interceptor to add auth token
    this.api.interceptors.request.use(
      (config) => {
        const token = this.getToken();
        if (token) {
          config.headers.Authorization = `Bearer ${token}`;
        }
        return config;
      },
      (error) => {
        return Promise.reject(error);
      }
    );

    // Response interceptor to handle errors
    this.api.interceptors.response.use(
      (response) => response,
      async (error) => {
        if (error.response?.status === 401) {
          // Try to refresh token
          const refreshToken = this.getRefreshToken();
          if (refreshToken) {
            try {
              const response = await this.api.post('/auth/refresh', {
                refresh_token: refreshToken,
              });
              this.setTokens(response.data.access_token, response.data.refresh_token);
              
              // Retry original request
              error.config.headers.Authorization = `Bearer ${response.data.access_token}`;
              return this.api.request(error.config);
            } catch (refreshError) {
              this.clearTokens();
              window.location.href = '/login';
            }
          } else {
            this.clearTokens();
            window.location.href = '/login';
          }
        }
        return Promise.reject(error);
      }
    );
  }

  // Token management
  private getToken(): string | null {
    return localStorage.getItem('access_token');
  }

  private getRefreshToken(): string | null {
    return localStorage.getItem('refresh_token');
  }

  private setTokens(accessToken: string, refreshToken: string): void {
    localStorage.setItem('access_token', accessToken);
    localStorage.setItem('refresh_token', refreshToken);
  }

  private clearTokens(): void {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
  }

  // Auth endpoints
  async login(credentials: LoginCredentials): Promise<AuthResponse> {
    const response = await this.api.post<AuthResponse>('/auth/login', {
      ...credentials,
      remember_me: true, // Always remember for PWA
    });
    this.setTokens(response.data.access_token, response.data.refresh_token);
    return response.data;
  }

  async logout(): Promise<void> {
    try {
      await this.api.post('/auth/logout');
    } finally {
      this.clearTokens();
    }
  }

  async getCurrentUser(): Promise<User> {
    const response = await this.api.get<User>('/auth/me');
    return response.data;
  }

  async updateUserPreferences(preferences: Record<string, any>): Promise<void> {
    await this.api.put('/auth/me/preferences', preferences);
  }

  // Chat endpoints
  async getChats(limit = 50, offset = 0): Promise<Chat[]> {
    const response = await this.api.get<Chat[]>('/chats', {
      params: { limit, offset },
    });
    return response.data;
  }

  async createChat(title: string, systemPrompt?: string, modelPreferences?: Record<string, any>): Promise<Chat> {
    const response = await this.api.post<Chat>('/chats', {
      title,
      system_prompt: systemPrompt,
      model_preferences: modelPreferences,
    });
    return response.data;
  }

  async getChat(chatId: string): Promise<Chat> {
    const response = await this.api.get<Chat>(`/chats/${chatId}`);
    return response.data;
  }

  async updateChat(chatId: string, updates: Partial<Chat>): Promise<Chat> {
    const response = await this.api.put<Chat>(`/chats/${chatId}`, updates);
    return response.data;
  }

  async deleteChat(chatId: string): Promise<void> {
    await this.api.delete(`/chats/${chatId}`);
  }

  async clearChatMessages(chatId: string): Promise<void> {
    await this.api.post(`/chats/${chatId}/clear`);
  }

  // Message endpoints
  async getChatMessages(chatId: string, limit = 100, offset = 0): Promise<Message[]> {
    const response = await this.api.get<Message[]>(`/chats/${chatId}/messages`, {
      params: { limit, offset },
    });
    return response.data;
  }

  async sendMessage(
    chatId: string,
    content: string,
    model?: string,
    temperature?: number
  ): Promise<Message> {
    const response = await this.api.post<Message>(`/chats/${chatId}/messages`, {
      content,
      model,
      temperature,
    });
    return response.data;
  }

  async deleteMessage(messageId: string): Promise<void> {
    await this.api.delete(`/messages/${messageId}`);
  }

  async searchMessages(query: string, chatId?: string, limit = 10): Promise<any[]> {
    const response = await this.api.post<any[]>('/messages/search', {
      query,
      chat_id: chatId,
      limit,
    });
    return response.data;
  }

  async uploadAttachment(messageId: string, file: File): Promise<any> {
    const formData = new FormData();
    formData.append('file', file);

    const response = await this.api.post(`/messages/${messageId}/attachments`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  }

  // Model endpoints
  async getModels(): Promise<ModelsResponse> {
    const response = await this.api.get<ModelsResponse>('/models');
    return response.data;
  }

  async checkModelStatus(): Promise<any> {
    const response = await this.api.get('/models/status');
    return response.data;
  }

  // WebSocket URL
  getWebSocketUrl(chatId: string): string {
    const wsUrl = process.env.REACT_APP_WS_URL || 'ws://localhost/ws';
    const token = this.getToken();
    return `${wsUrl}/chat/${chatId}?token=${token}`;
  }
}

export default new ApiService();