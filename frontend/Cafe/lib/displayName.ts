// プロフィールで決めた名前を、ブラウザに保存・取り出しする(焚火などで使う)
export const DISPLAY_NAME_KEY = "acafe_display_name";
export const MAX_DISPLAY_NAME = 20;

export function loadDisplayName(): string {
  try {
    return window.localStorage.getItem(DISPLAY_NAME_KEY) ?? "";
  } catch {
    return "";
  }
}

export function saveDisplayName(name: string): boolean {
  try {
    window.localStorage.setItem(DISPLAY_NAME_KEY, name.trim().slice(0, MAX_DISPLAY_NAME));
    return true;
  } catch {
    return false;
  }
}
