// Central notification system — toast (sonner) + confirm (AlertDialog).
// Replaces window.alert / window.confirm. Access via useNotify().
// Backed by shadcn/ui sonner (toasts) and AlertDialog (confirm).

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { toast } from "sonner";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

interface ConfirmState {
  message: string;
  title?: string;
  resolve: (ok: boolean) => void;
}

interface NotifyApi {
  success: (msg: string) => void;
  error: (msg: string) => void;
  info: (msg: string) => void;
  warning: (msg: string) => void;
  confirm: (msg: string) => Promise<boolean>;
}

const NotifyContext = createContext<NotifyApi>(null as unknown as NotifyApi);

export function NotificationProvider({ children }: { children: ReactNode }) {
  const [confirmState, setConfirmState] = useState<ConfirmState | null>(null);

  const confirm = useCallback((message: string) => {
    return new Promise<boolean>((resolve) => {
      setConfirmState({ message, resolve });
    });
  }, []);

  const api = useMemo<NotifyApi>(
    () => ({
      success: (m) => toast.success(m),
      error: (m) => toast.error(m),
      info: (m) => toast.info(m),
      warning: (m) => toast.warning(m),
      confirm,
    }),
    [confirm],
  );

  return (
    <NotifyContext.Provider value={api}>
      {children}

      {confirmState && (
        <AlertDialog
          open
          onOpenChange={(open: boolean) => {
            if (!open) {
              confirmState.resolve(false);
              setConfirmState(null);
            }
          }}
        >
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>{confirmState.title ?? "Are you sure?"}</AlertDialogTitle>
              <AlertDialogDescription>{confirmState.message}</AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction
                onClick={() => {
                  confirmState.resolve(true);
                  setConfirmState(null);
                }}
              >
                Confirm
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      )}
    </NotifyContext.Provider>
  );
}

export function useNotify() {
  return useContext(NotifyContext);
}

// Module-level helpers for non-hook contexts (the data store, plain functions).
// They talk to sonner's toast store directly, so they work anywhere the
// <Toaster /> is mounted — no React context needed.
export function notifyError(message: string) {
  toast.error(message);
}

export function notifySuccess(message: string) {
  toast.success(message);
}
