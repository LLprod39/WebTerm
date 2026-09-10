import * as Dropdown from "@radix-ui/react-dropdown-menu";
import { ChevronDown } from "lucide-react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui";
import {
  matchesNavigation,
  type NavigationGroup,
  type NavigationItem,
} from "./navigation";

function NavigationRow({
  items,
  pathname,
  label,
  moreLabel = "Ещё",
}: {
  items: NavigationItem[];
  pathname: string;
  label: string;
  moreLabel?: string;
}) {
  const primary = items.filter((item) => !item.advanced);
  const additional = items.filter((item) => item.advanced);
  const selectedAdditional = additional.find((item) =>
    matchesNavigation(item, pathname),
  );
  if (items.length < 2) return null;
  return (
    <nav className="section-navigation" aria-label={label}>
      {primary.map((item) => (
        <Link
          key={item.path}
          to={item.path}
          className="section-link"
          aria-current={matchesNavigation(item, pathname) ? "page" : undefined}
        >
          {item.label}
        </Link>
      ))}
      {additional.length > 0 && (
        <Dropdown.Root>
          <Dropdown.Trigger asChild>
            <Button
              variant="ghost"
              className={`section-more${selectedAdditional ? " active" : ""}`}
              aria-label={`${moreLabel}: ${label}`}
            >
              {selectedAdditional?.label ?? moreLabel} <ChevronDown size={14} />
            </Button>
          </Dropdown.Trigger>
          <Dropdown.Portal>
            <Dropdown.Content
              className="menu-content"
              sideOffset={6}
              align="start"
            >
              {additional.map((item) => (
                <Dropdown.Item key={item.path} asChild>
                  <Link
                    className="menu-item"
                    to={item.path}
                    aria-current={
                      matchesNavigation(item, pathname) ? "page" : undefined
                    }
                  >
                    <item.icon size={15} />
                    {item.label}
                  </Link>
                </Dropdown.Item>
              ))}
            </Dropdown.Content>
          </Dropdown.Portal>
        </Dropdown.Root>
      )}
    </nav>
  );
}

export function SectionNavigation({
  group,
  pathname,
}: {
  group: NavigationGroup;
  pathname: string;
}) {
  const items = group.items.filter(
    (item) => !item.hiddenInSection && !item.parentPath,
  );
  const parent = items.find((item) => matchesNavigation(item, pathname));
  const children = parent
    ? group.items.filter((item) => item.parentPath === parent.path)
    : [];
  if (items.length < 2 && children.length < 2) return null;
  return (
    <div className="section-navigation-stack">
      <NavigationRow
        items={items}
        pathname={pathname}
        label={group.label}
        moreLabel={group.id === "settings" ? "Дополнительно" : "Ещё"}
      />
      <NavigationRow
        items={children}
        pathname={pathname}
        label={parent?.label ?? group.label}
        moreLabel="Дополнительно"
      />
    </div>
  );
}
