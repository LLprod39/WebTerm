import { localize } from "@/lib/i18n";

export function getRunDialogCopy(mode: string, lang: string) {
  if (mode === "webhook") {
    return {
      title: localize(lang, "Webhook trigger", "Webhook Trigger"),
      description: localize(lang, "Webhook pipeline не запускается кнопкой Run. Сохраните граф и отправьте HTTP POST на webhook URL.", "Webhook pipelines do not start from Run. Save the graph, then send an HTTP POST request to the webhook URL."),
    };
  }
  if (mode === "schedule") {
    return {
      title: localize(lang, "Schedule trigger", "Scheduled Trigger"),
      description: localize(lang, "Schedule pipeline запускает планировщик. Сохраните граф, дальше run создаст cron trigger.", "Scheduled pipelines do not start from Run. Save the graph and let the scheduler create runs from the cron trigger."),
    };
  }
  if (mode === "monitoring") {
    return {
      title: localize(lang, "Monitoring trigger", "Monitoring Trigger"),
      description: localize(lang, "Monitoring pipeline ждёт alert от server monitoring. Сохраните граф, run появится при совпадении условий.", "Monitoring pipelines do not start from Run. Save the graph and let server monitoring open a matching alert."),
    };
  }
  return {
    title: localize(lang, "Запуск pipeline", "Run Pipeline"),
    description: localize(lang, "Выберите ручной trigger для старта, затем добавьте задачу и необязательный JSON context.", "Choose the manual trigger that should start this run, then add optional task text and JSON context."),
  };
}
