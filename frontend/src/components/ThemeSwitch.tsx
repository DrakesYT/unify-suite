import { setTheme, useTheme, type Theme } from "../theme";
import { MoonIcon, SunIcon } from "./icons";

const OPTIONS: { value: Theme; text: string; icon: typeof SunIcon }[] = [
  { value: "light", text: "Light", icon: SunIcon },
  { value: "dark", text: "Dark", icon: MoonIcon },
];

/** Light / Dark segmented switch for the top bar (labels hide on narrow screens). */
export function ThemeSwitch() {
  const theme = useTheme();
  return (
    <div
      role="radiogroup"
      aria-label="Colour theme"
      className="flex items-center gap-0.5 rounded-full bg-navy-900 p-1 ring-1 ring-white/[0.07] card-shadow"
    >
      {OPTIONS.map(({ value, text, icon: Icon }) => {
        const on = theme === value;
        return (
          <button
            key={value}
            role="radio"
            aria-checked={on}
            title={`${text} theme`}
            onClick={(e) => setTheme(value, e.currentTarget)}
            className={`flex items-center gap-1.5 rounded-full px-2 py-1 text-xs font-medium transition-colors duration-150 xl:px-2.5 ${
              on ? "bg-accent-purple text-on-accent" : "text-slate-400 hover:text-white"
            }`}
          >
            <Icon size={14} />
            <span className="hidden xl:inline">{text}</span>
          </button>
        );
      })}
    </div>
  );
}
