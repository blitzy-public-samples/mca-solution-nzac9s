import axios, { AxiosInstance } from 'axios';
import { RootState } from 'app/store';
import { Application, ApplicationCreate } from 'app/schema/applicationSchema';

const API_BASE_URL = process.env.REACT_APP_API_BASE_URL;

const createApiClient = (): AxiosInstance => {
  const instance = axios.create({
    baseURL: API_BASE_URL,
  });

  instance.interceptors.request.use((config) => {
    // HUMAN ASSISTANCE NEEDED
    // Add authentication logic here, e.g., adding a token to the headers
    // const token = getTokenFromStore();
    // if (token) {
    //   config.headers['Authorization'] = `Bearer ${token}`;
    // }
    return config;
  });

  instance.interceptors.response.use(
    (response) => response,
    (error) => {
      // HUMAN ASSISTANCE NEEDED
      // Add error handling logic here, e.g., refreshing token on 401 errors
      // if (error.response && error.response.status === 401) {
      //   // Refresh token logic
      // }
      return Promise.reject(error);
    }
  );

  return instance;
};

export const getApplications = async (page: number, limit: number): Promise<Application[]> => {
  const client = createApiClient();
  const response = await client.get('/applications', { params: { page, limit } });
  return response.data;
};

export const createApplication = async (applicationData: ApplicationCreate): Promise<Application> => {
  const client = createApiClient();
  const response = await client.post('/applications', applicationData);
  return response.data;
};

export const getApplicationById = async (id: string): Promise<Application> => {
  const client = createApiClient();
  const response = await client.get(`/applications/${id}`);
  return response.data;
};