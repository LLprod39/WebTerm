import { useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { KeyRound, ShieldCheck } from "lucide-react";
import { ApiError } from "@/api/client";
import { infrastructureApi, type ServerDetail } from "@/api/infrastructure";
import { Button, Feedback, Field, Panel, StatusBadge } from "@/components/ui";
interface HostChallenge {
  code: string;
  host_key?: { fingerprint_sha256: string; algorithm?: string };
  trusted_fingerprints?: string[];
  is_rotation?: boolean;
}
export function ServerSecurity({ server }: { server: ServerDetail }) {
  const client = useQueryClient();
  const [fingerprint, setFingerprint] = useState("");
  const [verified, setVerified] = useState(false);
  const [challenge, setChallenge] = useState<HostChallenge | null>(null);
  const test = useMutation({
    mutationKey: ["server-workspace", server.id],
    mutationFn: () => infrastructureApi.test(server.id),
    onSuccess: () => {
      setChallenge(null);
      void client.invalidateQueries({ queryKey: ["server", server.id] });
    },
    onError: (error) => {
      if (error instanceof ApiError) {
        const data = error.details as HostChallenge;
        if (data?.host_key) {
          setChallenge(data);
          setFingerprint("");
          setVerified(false);
        }
      }
    },
  });
  const enroll = useMutation({
    mutationKey: ["server-workspace", server.id],
    mutationFn: () =>
      infrastructureApi.test(server.id, {
        enroll_host_key: true,
        expected_host_key_fingerprint: fingerprint.trim(),
        replace_host_key: !!challenge?.is_rotation,
      }),
    onSuccess: () => {
      setChallenge(null);
      test.reset();
      void client.invalidateQueries({ queryKey: ["server", server.id] });
    },
  });
  function submit(e: FormEvent) {
    e.preventDefault();
    if (
      server.can_edit &&
      verified &&
      fingerprint.trim() === challenge?.host_key?.fingerprint_sha256 &&
      !test.isPending &&
      !enroll.isPending
    )
      enroll.mutate();
  }
  return (
    <Panel
      title="Безопасность SSH"
      description="Проверка идентичности сервера перед передачей учётных данных."
    >
      <div className="section-body stack">
        <div className="spread">
          <div className="row">
            <ShieldCheck size={20} />
            <strong>Доверенный ключ сервера</strong>
          </div>
          <StatusBadge
            status={
              !server.can_edit
                ? "unknown"
                : server.has_trusted_host_keys
                  ? "ready"
                  : "warning"
            }
          >
            {!server.can_edit
              ? "Управляет владелец"
              : server.has_trusted_host_keys
                ? "Подтверждён"
                : "Требуется проверка"}
          </StatusBadge>
        </div>
        {server.trusted_host_key_fingerprints.map((key) => (
          <pre key={key} className="code-block">
            {key}
          </pre>
        ))}
        <p className="muted text-sm">
          {server.can_edit
            ? "Сверьте SHA256-отпечаток с доверенным источником вашей организации. При изменении ключа требуется отдельное подтверждение."
            : "Доверенный ключ настраивает владелец сервера. Вы можете проверить доступное вам подключение."}
        </p>
        <Button
          disabled={!server.capabilities.connect_terminal || enroll.isPending}
          onClick={() => {
            enroll.reset();
            setChallenge(null);
            test.mutate();
          }}
          loading={test.isPending}
        >
          <KeyRound size={15} />
          Проверить подключение
        </Button>
        {challenge && server.can_edit && (
          <form onSubmit={submit}>
            <fieldset
              className="stack"
              disabled={enroll.isPending || test.isPending}
              style={{ border: 0, margin: 0, padding: 0, minWidth: 0 }}
            >
              <div className="notice notice-warning">
                {challenge.is_rotation
                  ? "Ключ сервера изменился. Проверьте причину ротации."
                  : "Первое подключение: подтвердите идентичность сервера."}
              </div>
              <div className="code-block mono">
                {challenge.host_key?.algorithm}
                <br />
                {challenge.host_key?.fingerprint_sha256}
              </div>
              <Field
                label="Проверенный SHA256-отпечаток"
                htmlFor="host-key-fingerprint"
              >
                <input
                  className="mono"
                  id="host-key-fingerprint"
                  value={fingerprint}
                  onChange={(e) => setFingerprint(e.target.value)}
                  required
                  placeholder="SHA256:…"
                />
              </Field>
              <label className="checkbox-field text-sm">
                <input
                  type="checkbox"
                  checked={verified}
                  onChange={(e) => setVerified(e.target.checked)}
                />
                Я сверил ключ с доверенным источником.
              </label>
              <Button
                type="submit"
                variant="primary"
                loading={enroll.isPending}
                disabled={
                  !verified ||
                  fingerprint.trim() !== challenge.host_key?.fingerprint_sha256
                }
              >
                {challenge.is_rotation
                  ? "Подтвердить замену ключа"
                  : "Сохранить доверенный ключ"}
              </Button>
            </fieldset>
          </form>
        )}
        {challenge && !server.can_edit && (
          <p className="notice notice-warning">
            Владелец сервера должен подтвердить SSH-ключ перед подключением.
          </p>
        )}
        <Feedback
          error={challenge ? enroll.error : test.error}
          success={
            test.isSuccess || enroll.isSuccess
              ? "SSH-подключение проверено"
              : undefined
          }
        />
      </div>
    </Panel>
  );
}
