import dayjs from 'dayjs';

export function formatCurrency(amount: number, currencyCode: string): string {
  const formatter = new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: currencyCode,
  });
  return formatter.format(amount);
}

export function formatDate(dateString: string, format: string): string {
  return dayjs(dateString).format(format);
}

// HUMAN ASSISTANCE NEEDED
// This function might need additional validation or error handling for different phone number formats
export function formatPhoneNumber(phoneNumber: string): string {
  const digits = phoneNumber.replace(/\D/g, '');
  
  if (digits.length === 10) {
    return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`;
  } else {
    return phoneNumber;
  }
}