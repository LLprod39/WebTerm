import { SettingsPageHeader } from "@/components/settings/SettingsPageHeader";
import { SettingsPageShell } from "@/components/settings/SettingsPageShell";
import { UiStylePicker } from "@/components/UiStylePicker";
import { AppearanceIcons } from "@/lib/app-icons";
import { localize, useI18n } from "@/lib/i18n";

export default function SettingsAppearancePage() {
  const { lang } = useI18n();

  return (
    <SettingsPageShell slot="settings-appearance" width="full">
      <h1 className="sr-only lg:hidden">{localize(lang, "Оформление", "Appearance")}</h1>
      <SettingsPageHeader
        icon={AppearanceIcons.picker}
        title={localize(lang, "Оформление", "Appearance")}
        description={localize(
          lang,
          "Выберите стиль интерфейса — превью показывает палитру и каркас экрана.",
          "Choose an interface style — each preview shows the palette and screen chrome.",
        )}
        className="hidden lg:block"
      />

      <UiStylePicker showIntro={false} />
    </SettingsPageShell>
  );
}
