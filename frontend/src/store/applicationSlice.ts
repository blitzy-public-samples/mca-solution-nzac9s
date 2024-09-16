import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import { Application } from '../schema/applicationSchema';

// HUMAN ASSISTANCE NEEDED
// The confidence level is below 0.8, so this code may need review and adjustments for production readiness.
// Please verify the structure and functionality of the slice, and make any necessary improvements.

interface ApplicationState {
  applications: Application[];
}

const initialState: ApplicationState = {
  applications: [],
};

const applicationSlice = createSlice({
  name: 'application',
  initialState,
  reducers: {
    setApplications: (state, action: PayloadAction<Application[]>) => {
      state.applications = action.payload;
    },
    addApplication: (state, action: PayloadAction<Application>) => {
      state.applications.push(action.payload);
    },
    updateApplication: (state, action: PayloadAction<Application>) => {
      const index = state.applications.findIndex(app => app.id === action.payload.id);
      if (index !== -1) {
        state.applications[index] = action.payload;
      }
    },
    removeApplication: (state, action: PayloadAction<string>) => {
      state.applications = state.applications.filter(app => app.id !== action.payload);
    },
  },
});

export const { setApplications, addApplication, updateApplication, removeApplication } = applicationSlice.actions;
export default applicationSlice.reducer;