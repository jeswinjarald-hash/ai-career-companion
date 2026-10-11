import { expect, test } from '@playwright/test'
import { pathForView, routeFromLocation, viewFromLocation } from '../../src/routing'

const at = (url: string) => { const parsed = new URL(url, 'http://localhost'); return { pathname: parsed.pathname, search: parsed.search } }

test('job deep links restore the view and the selected job', () => {
  expect(routeFromLocation(at('/jobs/JOB-0001'))).toEqual({ view: 'job-details', jobId: 'JOB-0001', applicationId: null })
  expect(routeFromLocation(at('/jobs/JOB%2F7'))).toEqual({ view: 'job-details', jobId: 'JOB/7', applicationId: null })
  expect(routeFromLocation(at('/jobs/')).jobId).toBeNull()
})

test('job-scoped pages restore the job from ?job=', () => {
  for (const [path, view] of [['/skills', 'skills'], ['/customize', 'customize'], ['/interview-prep', 'interview-prep']] as const) {
    expect(routeFromLocation(at(`${path}?job=JOB-0002`))).toEqual({ view, jobId: 'JOB-0002', applicationId: null })
  }
})

test('application deep links restore the selected application', () => {
  expect(routeFromLocation(at('/applications/42'))).toEqual({ view: 'application-details', jobId: null, applicationId: 42 })
  expect(routeFromLocation(at('/applications/not-a-number'))).toEqual({ view: 'application-details', jobId: null, applicationId: null })
  expect(routeFromLocation(at('/applications'))).toEqual({ view: 'applications', jobId: null, applicationId: null })
})

test('unknown paths fall back to the dashboard', () => {
  expect(viewFromLocation(at('/'))).toBe('dashboard')
  expect(viewFromLocation(at('/no-such-page'))).toBe('dashboard')
  expect(viewFromLocation(at('/settings'))).toBe('settings')
  expect(viewFromLocation(at('/resume/results'))).toBe('resume-results')
})

test('paths built for navigation round-trip through the parser', () => {
  expect(pathForView('skills', 'JOB-0003', null)).toBe('/skills?job=JOB-0003')
  expect(pathForView('careers', 'JOB-0003', null)).toBe('/careers')
  expect(pathForView('job-details', 'JOB-0003', null)).toBe('/jobs/JOB-0003')
  expect(pathForView('application-details', null, 9)).toBe('/applications/9')
  expect(pathForView('resume-results', null, null)).toBe('/resume/results')
  for (const path of ['/skills?job=JOB-0003', '/jobs/JOB-0003', '/applications/9', '/dashboard', '/resume/results']) {
    const route = routeFromLocation(at(path))
    expect(pathForView(route.view, route.jobId, route.applicationId)).toBe(path)
  }
})
