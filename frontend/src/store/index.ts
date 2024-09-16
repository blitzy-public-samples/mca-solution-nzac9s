import { configureStore } from '@reduxjs/toolkit';
import { applicationReducer } from './applicationSlice';
import { userReducer } from './userSlice';

const store = configureStore({
  reducer: {
    application: applicationReducer,
    user: userReducer,
  },
  middleware: (getDefaultMiddleware) => getDefaultMiddleware(),
  devTools: process.env.NODE_ENV !== 'production',
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;

export default store;