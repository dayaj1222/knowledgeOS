// Compatibility barrel for the frontend API. New code can import a focused
// module directly; existing screens may continue importing from `../api`.
export * from "./api/core/client";
export * from "./api/core/types";
export * from "./api/library";
export * from "./api/resources";
export * from "./api/study";
export * from "./api/chat";
