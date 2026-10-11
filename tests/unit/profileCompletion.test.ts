import { expect, test } from '@playwright/test'
import { PROFILE_COMPLETION_FIELDS, profileCompletion } from '../../src/lib/profileCompletion'

// Defect D regression: name and e-mail are always present after registration and must
// not make an empty profile look partly complete.
const empty = {
  education: null, degree: null, specialization: null, experience_level: null,
  career_interests: [], target_roles: [], skills: [], career_goals: null,
}

test('a newly registered profile is 0% complete', () => {
  expect(profileCompletion(empty)).toEqual({ filled: 0, total: 8, percent: 0 })
})

test('name and e-mail are not completion criteria', () => {
  expect(PROFILE_COMPLETION_FIELDS).not.toContain('full_name')
  expect(PROFILE_COMPLETION_FIELDS).not.toContain('email')
  expect(profileCompletion({ ...empty, full_name: 'Alex Sample', email: 'alex.sample@example.com' } as typeof empty).percent).toBe(0)
})

test('a partial profile counts only the details actually filled in', () => {
  expect(profileCompletion({ ...empty, degree: 'B.Tech', skills: ['Python', 'SQL'] })).toEqual({ filled: 2, total: 8, percent: 25 })
})

test('whitespace-only text and blank list items do not count', () => {
  expect(profileCompletion({ ...empty, education: '   ', career_goals: '', target_roles: [' '] }).filled).toBe(0)
})

test('a complete profile is 100%', () => {
  expect(profileCompletion({
    education: 'Example Institute of Technology', degree: 'B.Tech', specialization: 'Computer Science', experience_level: 'Student',
    career_interests: ['Backend development'], target_roles: ['Software Engineer Intern'], skills: ['Python'], career_goals: 'Become a backend engineer.',
  })).toEqual({ filled: 8, total: 8, percent: 100 })
})
