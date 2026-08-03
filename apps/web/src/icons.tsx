// One icon library — lucide. These wrappers pin sizes/weights so every
// call site stays consistent and no other file needs to know the source.
import {
  ArrowUp,
  ChevronDown,
  Globe,
  LogOut,
  Maximize2,
  PanelLeft,
  Pencil,
  Plus,
  Search,
  Square,
  X,
} from "lucide-react";

export const IconPanel = () => <PanelLeft size={16} strokeWidth={1.8} />;
export const IconPlus = () => <Plus size={16} strokeWidth={2} />;
export const IconSearch = () => <Search size={14} strokeWidth={1.8} />;
export const IconX = () => <X size={14} strokeWidth={2} />;
export const IconLogout = () => <LogOut size={15} strokeWidth={1.8} />;
export const IconPencil = () => <Pencil size={13} strokeWidth={1.8} />;
export const IconExpand = () => <Maximize2 size={14} strokeWidth={1.8} />;
export const IconGlobe = () => <Globe size={16} strokeWidth={1.8} />;
export const IconArrowUp = () => <ArrowUp size={17} strokeWidth={2.4} />;
export const IconStop = () => <Square size={14} strokeWidth={2} fill="currentColor" />;
export const IconChevronDown = () => <ChevronDown size={22} strokeWidth={2.8} />;
