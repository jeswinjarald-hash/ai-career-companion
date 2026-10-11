// Compile-time contract check between the backend (types generated from FastAPI's
// OpenAPI schema by `npm run api:types`) and the hand-written types the services use.
// Nothing here runs or ships: `tsc -b` fails if a backend response no longer satisfies
// what the frontend reads, or a request payload the frontend sends is no longer accepted.
// When it fails, regenerate with `npm run api:types` and reconcile the named type.
//
// Known limits (not expressible in the OpenAPI schema or in TypeScript):
//  * free-form dict fields are checked only as dicts (see the two exclusions below);
//  * int vs float, string formats and Pydantic constraints (min_length, ge/le, max_length)
//    are not compared — TypeScript sees them all as number/string;
//  * key checks on request payloads are top-level only; no request body currently has
//    nested objects with fixed keys (bullet_edits is a free-form string map);
//  * a frontend response type that marks a field optional (`?:`) is not flagged if the
//    backend drops that field. Response types are written with required fields for this reason.
import type { components } from './generated/schema'
import type { Application, ApplicationReminder, ApplicationReminders, ApplicationSummary, ApplicationUpdate, DatasetApplicationCreate, ManualApplicationCreate } from '../services/applicationService'
import type { AssistantResponse, ConversationDetail, ConversationSummary, CreateConversationPayload, MessageOut, SendMessagePayload, SuggestedAction } from '../services/assistantService'
import type { AuthSession, AuthUser, login, registerAccount } from '../services/authService'
import type { ApplicationCustomization, ApplicationCustomizationEditPayload, ApplicationCustomizationSummary } from '../services/customizationService'
import type { InterviewPreparation, InterviewPreparationSummary, MockAnswerEvaluation, MockAnswerPayload } from '../services/interviewPrepService'
import type { JobPosting, JobSearchResult } from '../services/jobService'
import type { CandidateProfile, CandidateProfilePayload } from '../services/profileService'
import type { CandidateContext, JobMatchResult, ResumeExtraction, ResumeRecord, StructuredResume } from '../services/resumeService'
import type { SkillGapAnalysis } from '../services/skillGapService'

type S = components['schemas']
// Pydantic leaves fields that have a default out of the schema's `required` list, so they
// generate as optional; but FastAPI serializes every declared field of a response_model
// (no route uses response_model_exclude_unset/none), so in a response they are always present.
type Serialized<T> = T extends Array<infer Item> ? Array<Serialized<Item>> : T extends object ? { [K in keyof T]-?: Serialized<Exclude<T[K], undefined>> } : T
// Response direction: everything the backend returns must fit what the frontend expects.
type Reads<Backend, Frontend> = [Serialized<Backend>] extends [Frontend] ? true : { backendResponseNoLongerMatches: Frontend }
// Request direction: every value the frontend sends must be accepted by the backend model,
// and every key it sends must be declared there. Structural typing alone allows extra
// keys, but the backend rejects them (extra="forbid" models answer 422) or silently
// drops them (the Pydantic default), so an undeclared key is drift either way.
type UndeclaredKeys<Frontend, Backend> = Exclude<keyof Frontend, keyof Backend>
type Sends<Frontend, Backend> = [Frontend] extends [Backend]
  ? [UndeclaredKeys<Frontend, Backend>] extends [never] ? true : { frontendSendsKeysTheBackendDoesNotDeclare: UndeclaredKeys<Frontend, Backend> }
  : { backendNoLongerAcceptsPayload: Frontend }
type Expect<T extends true> = T

export type ContractChecks = [
  Expect<Reads<S['AuthResponse'], AuthSession>>,
  Expect<Sends<Parameters<typeof registerAccount>[0], S['RegisterRequest']>>,
  Expect<Sends<Parameters<typeof login>[0], S['LoginRequest']>>,
  Expect<Reads<S['UserResponse'], AuthUser>>,
  Expect<Reads<S['CandidateProfileResponse'], CandidateProfile>>,
  Expect<Sends<CandidateProfilePayload, S['CandidateProfileUpdate']>>,
  Expect<Sends<CandidateProfilePayload, S['CandidateProfileCreate']>>,
  Expect<Reads<S['ResumeResponse'], ResumeRecord>>,
  Expect<Reads<S['ResumeExtractionResponse'], ResumeExtraction>>,
  Expect<Reads<S['CandidateContextResponse'], CandidateContext>>,
  Expect<Reads<S['JobMatchResult'], JobMatchResult>>,
  Expect<Reads<S['JobSearchResult'], JobSearchResult>>,
  Expect<Reads<S['JobPosting'], JobPosting>>,
  Expect<Reads<S['SkillGapAnalysis'], SkillGapAnalysis>>,
  Expect<Reads<S['ApplicationCustomization'], ApplicationCustomization>>,
  Expect<Reads<S['ApplicationCustomizationSummary'], ApplicationCustomizationSummary>>,
  Expect<Sends<ApplicationCustomizationEditPayload, S['ApplicationCustomizationEditPayload']>>,
  Expect<Reads<S['InterviewPreparation'], InterviewPreparation>>,
  Expect<Reads<S['InterviewPreparationSummary'], InterviewPreparationSummary>>,
  Expect<Reads<S['MockAnswerEvaluation'], MockAnswerEvaluation>>,
  Expect<Sends<MockAnswerPayload, S['MockAnswerRequest']>>,
  Expect<Sends<CreateConversationPayload, S['CreateConversationRequest']>>,
  Expect<Sends<SendMessagePayload, S['SendMessageRequest']>>,
  Expect<Reads<S['ConversationSummary'], ConversationSummary>>,
  Expect<Reads<S['ConversationDetail'], ConversationDetail>>,
  Expect<Reads<S['MessageOut'], MessageOut>>,
  Expect<Reads<S['SuggestedAction'], SuggestedAction>>,
  Expect<Reads<S['AssistantResponse'], AssistantResponse>>,
  Expect<Reads<S['ApplicationResponse'], Application>>,
  // status_counts is dict[str, int] in the schema; application_service.py fills it with one
  // key per APPLICATION_STATUSES entry, which the frontend types as Record<ApplicationStatus, number>.
  Expect<Reads<S['ApplicationSummary'], Omit<ApplicationSummary, 'status_counts'> & { status_counts: Record<string, number> }>>,
  Expect<Reads<S['ApplicationReminder'], ApplicationReminder>>,
  Expect<Reads<S['ApplicationRemindersResponse'], ApplicationReminders>>,
  Expect<Sends<DatasetApplicationCreate, S['ApplicationCreate']>>,
  Expect<Sends<ManualApplicationCreate, S['ApplicationCreate']>>,
  Expect<Sends<ApplicationUpdate, S['ApplicationUpdate']>>,
  // `data` is a free-form dict in the schema, so only its envelope can be checked here;
  // its shape is covered by the backend structured-resume tests and the e2e upload journey.
  Expect<Reads<S['StructuredResumeResponse'], Omit<StructuredResume, 'data'> & { data: Record<string, unknown> }>>,
]
