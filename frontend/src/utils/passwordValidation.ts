export const SPECIAL_CHARS_REGEX = /[-!@#$%^&*(),.?":{}|<>_=+`~/\\[\];]/

export const passwordRules = {
  required: 'Password is required',
  minLength: { value: 8, message: 'Min 8 characters' },
  maxLength: { value: 72, message: 'Max 72 characters' },
  pattern: {
    value: /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[-!@#$%^&*(),.?":{}|<>_=+`~/\\[\];]).+$/,
    message: 'Must contain uppercase, lowercase, number, and special character'
  },
  validate: {
    isAscii: (val: string) => /^[\x20-\x7E]+$/.test(val) || 'Password must contain only printable ASCII characters'
  }
}

export const confirmPasswordRules = (watchPassword: string) => ({
  required: 'Confirm password is required',
  validate: (val: string) => {
    if (watchPassword && val !== watchPassword) {
      return 'Passwords do not match';
    }
    return true;
  }
})
