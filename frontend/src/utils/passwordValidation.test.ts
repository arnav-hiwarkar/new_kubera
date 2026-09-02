import { describe, it, expect } from 'vitest'
import { passwordRules, confirmPasswordRules, SPECIAL_CHARS_REGEX } from './passwordValidation'

describe('passwordRules', () => {
  it('validates minimum and maximum length bounds', () => {
    expect(passwordRules.minLength.value).toBe(8)
    expect(passwordRules.maxLength.value).toBe(72)
  })

  it('accepts valid complex passwords', () => {
    const validPasswords = [
      'Valid1!Pass',
      'A1!aaaaa', // exactly 8 chars
      'A' + 'a'.repeat(68) + '1!', // exactly 72 chars
      'P@ssw0rd2026',
      'Complex_Password#99',
    ]

    for (const pwd of validPasswords) {
      expect(passwordRules.pattern.value.test(pwd)).toBe(true)
    }
  })

  it('rejects passwords missing character classes', () => {
    // Missing uppercase
    expect(passwordRules.pattern.value.test('valid1!pass')).toBe(false)
    // Missing lowercase
    expect(passwordRules.pattern.value.test('VALID1!PASS')).toBe(false)
    // Missing digit
    expect(passwordRules.pattern.value.test('Valid!Pass')).toBe(false)
    // Missing special char
    expect(passwordRules.pattern.value.test('Valid1Pass')).toBe(false)
  })

  it('rejects passwords with non-ASCII or non-printable characters', () => {
    expect(passwordRules.validate.isAscii('Pässwörd1!')).not.toBe(true)
    expect(passwordRules.validate.isAscii('ПарольA1!b')).not.toBe(true)
    expect(passwordRules.validate.isAscii('密码Abc1!xx')).not.toBe(true)
    expect(passwordRules.validate.isAscii('Valid1!Pass\n')).not.toBe(true)
    // Valid printable ASCII should pass
    expect(passwordRules.validate.isAscii('Valid1!Pass')).toBe(true)
  })

  it('supports all required enterprise special characters', () => {
    const specialChars = '-!@#$%^&*(),.?":{}|<>_=+`~/\\\[\];'
    for (const ch of specialChars) {
      expect(SPECIAL_CHARS_REGEX.test(ch)).toBe(true)
      const pwd = `Valid1${ch}Pass`
      expect(passwordRules.pattern.value.test(pwd)).toBe(true)
    }
  })
})

describe('confirmPasswordRules', () => {
  it('passes when confirm password matches password', () => {
    const rules = confirmPasswordRules('Valid1!Pass')
    expect(rules.validate('Valid1!Pass')).toBe(true)
  })

  it('fails when confirm password does not match password', () => {
    const rules = confirmPasswordRules('Valid1!Pass')
    expect(rules.validate('Different1!Pass')).toBe('Passwords do not match')
  })
})
