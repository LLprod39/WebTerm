import { localize } from "@/lib/i18n";

export function getRunDialogCopy(mode: string, lang: string) {
  if (mode === "webhook") {
    return {
      title: localize(lang, "Webhook-триггер", "Webhook Trigger"),
      description: localize(lang, "Сохраните пайплайн и отправьте POST-запрос на адрес webhook. Кнопка запуска для него не используется.", "Save the pipeline and send a POST request to its webhook URL. The Run button is not used for this trigger."),
    };
  }
  if (mode === "schedule") {
    return {
      title: localize(lang, "Триггер расписания", "Scheduled Trigger"),
      description: localize(lang, "Сохраните пайплайн. Планировщик будет запускать его по указанному расписанию.", "Save the pipeline. The scheduler will run it at the configured times."),
    };
  }
  if (mode === "monitoring") {
    return {
      title: localize(lang, "Триггер мониторинга", "Monitoring Trigger"),
      description: localize(lang, "Сохраните пайплайн. Он запустится, когда мониторинг обнаружит подходящее событие.", "Save the pipeline. It will run when monitoring detects a matching event."),
    };
  }
  return {
    title: localize(lang, "Запуск пайплайна", "Run pipeline"),
    description: localize(lang, "Выберите ручной триггер для старта, затем добавьте задачу и необязательный JSON-контекст.", "Choose the manual trigger that should start this run, then add optional task text and JSON context."),
  };
}
