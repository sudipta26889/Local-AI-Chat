import React, { createContext, useContext, useEffect } from 'react';
import { useAuthStore } from '../services/auth';

interface AuthContextType {
  // We're using Zustand store directly, so this is mainly for provider setup
}

const AuthContext = createContext<AuthContextType>({});

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

interface AuthProviderProps {
  children: React.ReactNode;
}

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const checkAuth = useAuthStore((state) => state.checkAuth);

  useEffect(() => {
    // Check auth status on mount
    checkAuth();
  }, [checkAuth]);

  return <AuthContext.Provider value={{}}>{children}</AuthContext.Provider>;
};