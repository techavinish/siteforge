// One icon library — lucide. These wrappers pin sizes/weights so every
// call site stays consistent and no other file needs to know the source.
import {
  ArrowUp,
  ChevronDown,
  ChevronRight,
  Copy,
  Inbox,
  RotateCcw,
  RefreshCw,
  Globe,
  LogOut,
  Maximize2,
  PanelLeft,
  Paperclip,
  Pencil,
  Plus,
  Search,
  Square,
  X,
} from "lucide-react";

export const IconPanel = () => <PanelLeft size={17} strokeWidth={1.9} />;
export const IconPlus = () => <Plus size={16} strokeWidth={2.1} />;
export const IconSearch = () => <Search size={14} strokeWidth={1.9} />;
export const IconX = () => <X size={15} strokeWidth={2.1} />;
export const IconLogout = () => <LogOut size={16} strokeWidth={1.9} />;
export const IconPencil = () => <Pencil size={14} strokeWidth={1.9} />;
export const IconExpand = () => <Maximize2 size={15} strokeWidth={1.9} />;
export const IconGlobe = () => <Globe size={17} strokeWidth={1.9} />;
export const IconArrowUp = () => <ArrowUp size={18} strokeWidth={2.4} />;
export const IconStop = () => <Square size={15} strokeWidth={2} fill="currentColor" />;
export const IconChevronDown = () => <ChevronDown size={28} strokeWidth={2.6} />;
export const IconChevronSmall = () => <ChevronRight size={13} strokeWidth={2.2} />;
export const IconCopy = () => <Copy size={14} strokeWidth={1.9} />;
export const IconRetry = () => <RotateCcw size={14} strokeWidth={1.9} />;
export const IconClip = () => <Paperclip size={17} strokeWidth={1.9} />;
export const IconInbox = () => <Inbox size={14} strokeWidth={1.9} />;
export const IconGlobeSm = () => <Globe size={14} strokeWidth={1.9} />;
export const IconRefresh = () => <RefreshCw size={14} strokeWidth={1.9} />;
