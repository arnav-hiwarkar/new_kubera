export const passwordRules = {
  required: 'Password is required',
  minLength: { value: 8, message: 'Min 8 characters' },
  maxLength: { value: 72, message: 'Max 72 characters' },
  pattern: {
    value: /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[-!@#$%^&*(),.?":{}|<>_=+`~/\\[\];]).+$/,
    message: 'Must contain uppercase, lowercase, number, and special character'
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
