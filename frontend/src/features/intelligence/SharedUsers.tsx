import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { ErrorState, Field, LoadingState } from "@/components/ui";
export function SharedUsers({
  ids,
  onChange,
}: {
  ids: number[];
  onChange: (ids: number[]) => void;
}) {
  const q = useQuery({
    queryKey: ["intelligence", "share-users"],
    queryFn: () =>
      api.get<{ id: number; username: string }[]>("/api/studio/share-users/"),
  });
  return (
    <Field
      label="Персональные назначения"
      description="Пользователи получают доступ к этой конфигурации независимо от общего доступа."
    >
      {q.isPending ? (
        <LoadingState />
      ) : q.error ? (
        <ErrorState error={q.error} />
      ) : (
        <div className="intel-checkbox-list">
          {q.data?.map((user) => (
            <label key={user.id}>
              <input
                type="checkbox"
                checked={ids.includes(user.id)}
                onChange={(e) =>
                  onChange(
                    e.target.checked
                      ? [...ids, user.id]
                      : ids.filter((id) => id !== user.id),
                  )
                }
              />
              {user.username}
            </label>
          ))}
        </div>
      )}
    </Field>
  );
}
