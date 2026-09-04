import { nanoid } from "nanoid";

export function getOrCreateRequestId(): string {
    const existingRequestId = (typeof window !== "undefined" && window.localStorage.getItem("requestId")) || null;
    if (existingRequestId) {
        return existingRequestId;
    }

    const newRequestId = nanoid()
    if ((typeof window !== "undefined") && window.localStorage) {
        window.localStorage.setItem("requestId", newRequestId);
    }
    return newRequestId;
}