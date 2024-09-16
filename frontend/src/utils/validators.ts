import { z } from 'zod';

export const validateEmail = (email: string): boolean => {
  const emailSchema = z.string().email();
  return emailSchema.safeParse(email).success;
};

// HUMAN ASSISTANCE NEEDED
// This function may need additional validation rules or refinement for production use
export const validateTaxId = (taxId: string): boolean => {
  const cleanTaxId = taxId.replace(/[-\s]/g, '');
  if (cleanTaxId.length !== 9 || !/^\d+$/.test(cleanTaxId)) {
    return false;
  }
  const firstTwoDigits = parseInt(cleanTaxId.slice(0, 2), 10);
  return firstTwoDigits >= 1 && firstTwoDigits <= 99;
};

// HUMAN ASSISTANCE NEEDED
// This function may need additional validation rules or refinement for production use
export const validateSSN = (ssn: string): boolean => {
  const cleanSSN = ssn.replace(/[-\s]/g, '');
  if (cleanSSN.length !== 9 || !/^\d+$/.test(cleanSSN)) {
    return false;
  }
  if (cleanSSN === '000000000' || cleanSSN === '111111111' || cleanSSN === '222222222' ||
      cleanSSN === '333333333' || cleanSSN === '444444444' || cleanSSN === '555555555' ||
      cleanSSN === '666666666' || cleanSSN === '777777777' || cleanSSN === '888888888' ||
      cleanSSN === '999999999') {
    return false;
  }
  if (cleanSSN.startsWith('666') || cleanSSN.startsWith('9')) {
    return false;
  }
  return true;
};