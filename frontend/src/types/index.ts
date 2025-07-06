export interface User {
  id: string;
  ldap_uid: string;
  email?: string;
  display_name?: string;
  created_at: string;
  last_login?: string;
  preferences?: Record<string, any>;
}

export interface Chat {
  id: string;
  user_id: string;
  title: string;
  system_prompt?: string;
  model_preferences: Record<string, any>;
  created_at: string;
  updated_at: string;
  message_count?: number;
}

export interface Message {
  id: string;
  chat_id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  model_used?: string;
  tokens_used?: number;
  created_at: string;
  attachments?: Attachment[];
}

export interface Attachment {
  id: string;
  message_id: string;
  file_name: string;
  file_type?: string;
  file_size?: number;
  created_at: string;
}

export interface Model {
  name: string;
  service: string;
  service_type: string;
  endpoint: string;
  available: boolean;
  is_default: boolean;
}

export interface Service {
  name: string;
  type: string;
  url: string;
  default_model: string;
  models: string[];
  is_healthy: boolean;
  is_default_service: boolean;
}

export interface ModelsResponse {
  services: Service[];
  models: Model[];
  default_service: string;
  default_model: string;
}

export interface LoginCredentials {
  username: string;
  password: string;
}

export interface AuthResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export interface WebSocketMessage {
  type: 'connected' | 'user_message' | 'stream_start' | 'stream_chunk' | 'stream_end' | 'stream_complete' | 'stream_error' | 'error' | 'pong';
  message_id?: string;
  content?: string;
  full_content?: string;
  error?: string;
  chat_id?: string;
  user_id?: string;
  created_at?: string;
  tokens_used?: number;
  complete?: boolean;
  final?: boolean;
}