import axios from 'axios';
import { RootState } from 'app/store';
import { createApiClient } from './api';

export const login = async (username: string, password: string): Promise<void> => {
  try {
    const apiClient = createApiClient();
    const response = await apiClient.post('/auth/login', { username, password });
    const { token } = response.data;
    
    localStorage.setItem('authToken', token);
    
    // HUMAN ASSISTANCE NEEDED
    // TODO: Update auth state in Redux store
    // This part requires knowledge of the specific Redux setup and actions
    // Example: dispatch(setAuthToken(token));
  } catch (error) {
    console.error('Login failed:', error);
    throw error;
  }
};

export const logout = (): void => {
  localStorage.removeItem('authToken');
  
  // HUMAN ASSISTANCE NEEDED
  // TODO: Update auth state in Redux store
  // This part requires knowledge of the specific Redux setup and actions
  // Example: dispatch(clearAuthToken());
};

export const getAuthToken = (): string | null => {
  return localStorage.getItem('authToken');
};