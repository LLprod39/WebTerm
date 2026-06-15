import { localize } from "@/lib/i18n";

export function getRunDialogCopy(mode: string, lang: string) {
  if (mode === "webhook") {
    return {
      title: localize(lang, "Webhook-триггер", "Webhook Trigger"),
      description: localize(lang, "Webhook pipeline не запускается кнопкой запуска. Сохраните граф и отправьте HTTP POST на webhook URL.", "Webhook pipelines do not start from Run. Save the graph, then send an HTTP POST request to the webhook URL."),
    };
  }
  if (mode === "schedule") {
    return {
      title: localize(lang, "Триггер расписания", "Scheduled Trigger"),
      description: localize(lang, "Pipeline по расписанию запускает планировщик. Сохраните граф, дальше запуск создаст cron-триггер.", "Scheduled pipelines do not start from Run. Save the graph and let the scheduler create runs from the cron trigger."),
    };
  }
  if (mode === "monitoring") {
    return {
      title: localize(lang, "Триггер мониторинга", "Monitoring Trigger"),
      description: localize(lang, "Pipeline мониторинга ждёт алерт от мониторинга сервера. Сохраните граф, запуск появится при совпадении условий.", "Monitoring pipelines do not start from Run. Save the graph and let server monitoring open a matching alert."),
    };
  }
  return {
    title: localize(lang, "Запуск pipeline", "Run Pipeline"),
    description: localize(lang, "Выберите ручной триггер для старта, затем добавьте задачу и необязательный JSON-контекст.", "Choose the manual trigger that should start this run, then add optional task text and JSON context."),
  };
}
