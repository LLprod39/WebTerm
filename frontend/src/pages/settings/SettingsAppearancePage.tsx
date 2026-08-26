import { SettingsPageHeader } from "@/components/settings/SettingsPageHeader";
import { UiStylePicker } from "@/components/UiStylePicker";
import { AppearanceIcons } from "@/lib/app-icons";
import { localize, useI18n } from "@/lib/i18n";

export default function SettingsAppearancePage() {
  const { lang } = useI18n();

  return (
    <div data-ui-slot="settings-appearance" className="space-y-5">
      <h1 className="sr-only lg:hidden">{localize(lang, "Оформление", "Appearance")}</h1>
      <SettingsPageHeader
        icon={AppearanceIcons.picker}
        title={localize(lang, "Оформление", "Appearance")}
        description={localize(lang, "Выберите стиль интерфейса.", "Choose an interface style.")}
        className="hidden lg:block"
      />

      <UiStylePicker showIntro={false} />
    </div>
  );
}
