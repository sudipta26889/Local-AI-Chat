import { WebSocketMessage } from '../types';

export class ChatWebSocket {
  private ws: WebSocket | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 10;
  private reconnectDelay = 1000;
  private pingInterval: NodeJS.Timeout | null = null;
  private isReconnecting = false;
  private lastMessageTime = Date.now();

  constructor(
    private url: string,
    private onMessage: (message: WebSocketMessage) => void,
    private onError?: (error: string) => void,
    private onConnect?: () => void,
    private onDisconnect?: () => void
  ) {}

  connect(): void {
    try {
      this.ws = new WebSocket(this.url);

      this.ws.onopen = () => {
        console.log('WebSocket connected');
        this.reconnectAttempts = 0;
        this.isReconnecting = false;
        this.lastMessageTime = Date.now();
        this.startPing();
        this.onConnect?.();
      };

      this.ws.onmessage = (event) => {
        try {
          this.lastMessageTime = Date.now();
          const message: WebSocketMessage = JSON.parse(event.data);
          this.onMessage(message);
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error, 'Raw data:', event.data);
        }
      };

      this.ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        this.onError?.('WebSocket connection error');
      };

      this.ws.onclose = (event) => {
        console.log('WebSocket disconnected', event.code, event.reason);
        this.stopPing();
        this.onDisconnect?.();
        
        // Only attempt reconnect if not manually disconnected
        if (event.code !== 1000 && !this.isReconnecting) {
          this.isReconnecting = true;
          this.attemptReconnect();
        }
      };
    } catch (error) {
      console.error('Failed to create WebSocket:', error);
      this.onError?.('Failed to connect to chat server');
    }
  }

  private attemptReconnect(): void {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      console.log(`Attempting to reconnect (${this.reconnectAttempts}/${this.maxReconnectAttempts})...`);
      
      // Exponential backoff with jitter
      const delay = Math.min(this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1), 30000);
      const jitter = Math.random() * 1000;
      
      setTimeout(() => {
        this.connect();
      }, delay + jitter);
    } else {
      this.onError?.('Failed to reconnect to chat server after multiple attempts');
    }
  }

  private startPing(): void {
    this.pingInterval = setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.send({ type: 'ping' });
      }
    }, 30000); // Ping every 30 seconds
  }

  private stopPing(): void {
    if (this.pingInterval) {
      clearInterval(this.pingInterval);
      this.pingInterval = null;
    }
  }

  send(data: any): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    } else {
      this.onError?.('WebSocket is not connected');
    }
  }

  sendMessage(content: string, model?: string, temperature?: number, maxTokens?: number): void {
    this.send({
      type: 'message',
      content,
      model,
      temperature,
      max_tokens: maxTokens,
    });
  }

  disconnect(): void {
    this.stopPing();
    this.isReconnecting = false;
    this.reconnectAttempts = this.maxReconnectAttempts; // Prevent reconnection
    if (this.ws) {
      this.ws.close(1000, 'Manual disconnect');
      this.ws = null;
    }
  }

  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}