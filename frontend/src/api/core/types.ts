export interface Course { id: number; user_id: number; name: string; code: string; type: string; instructor?: string | null; credits: number; status: string; color?: string | null; module_count?: number; topic_count?: number }
export interface Module { id: number; course_id: number; name: string; order_index: number; topic_count?: number }
export interface Topic { id: number; module_id: number; parent_topic_id?: number | null; name: string; description?: string | null; order_index: number; priority: number; prerequisite_ids: number[]; passage_count?: number }
export interface Proficiency { user_id: number; topic_id: number; score: number; weak_points: unknown[]; strengths: unknown[]; preferred_method: string }
export interface Resource { id: number; user_id: number; course_id: number; name: string; type: string; file_path: string; status?: string; error?: string | null; module_id?: number | null; topic_id?: number | null; passage_count?: number }
export interface Passage { id: number; resource_id: number; content: string; index_order: number; page_start?: number; page_end?: number; topic_id?: number | null; section_path?: string | null }
export interface Question { id: number; topic_id: number; text: string; type: string; expected_key_points: unknown[]; images?: string | null }
export interface Assessment { id: number; user_id: number; status: string }
export interface Attempt { id: number; user_id: number; assessment_id: number; question_id: number; user_answer?: string | null; score: number; feedback?: string | null; matched_key_points: string[]; missed_key_points: string[]; status: string; excluded: boolean }
export interface Deadline { id: number; user_id: number; course_id: number; topic_id?: number | null; title: string; due_date: string; weight: number }
export interface Plan { id: number; user_id: number; slot_id?: number | null; topic_id: number; suggested_duration_minutes: number; status: string; generated_at: string }
export interface Preference { user_id: number; session_length_minutes: number; daily_goal_minutes: number; preferred_start?: string | null; preferred_end?: string | null; tutor_instructions?: string | null; tutor_style: string; tutor_verbosity: string; default_quiz_count: number; default_difficulty: string; review_batch_size: number }
export interface StudyLog { id: number; user_id: number; topic_id: number; resource_id?: number | null; passage_id?: number | null; plan_id?: number | null; minutes_spent: number; confidence_after?: number | null; created_at?: string | null }
export interface EngineStatus { model: string; endpoint: string; threading: string; database: string; courses: number; topics: number; conversations: number }
