export interface DiscoveryValues {
  after_hours?: string | null;
  current_tool?: string | null;
  hiring_front_desk?: number | null;
  missed_calls?: string | null;
  answering_spend?: number | null;
}

const EMPTY: DiscoveryValues = {};

export function emptyDiscovery(): DiscoveryValues {
  return { ...EMPTY };
}

export function hasDiscoveryValues(v: DiscoveryValues | null | undefined): boolean {
  if (!v) return false;
  return Boolean(
    v.after_hours
    || v.current_tool
    || v.hiring_front_desk != null
    || v.missed_calls
    || v.answering_spend != null,
  );
}

export function discoveryForSubmit(v: DiscoveryValues): DiscoveryValues | undefined {
  if (!hasDiscoveryValues(v)) return undefined;
  const out: DiscoveryValues = {};
  if (v.after_hours) out.after_hours = v.after_hours;
  if (v.current_tool?.trim()) out.current_tool = v.current_tool.trim();
  if (v.hiring_front_desk != null) out.hiring_front_desk = v.hiring_front_desk;
  if (v.missed_calls) out.missed_calls = v.missed_calls;
  if (v.answering_spend != null && !Number.isNaN(v.answering_spend)) {
    out.answering_spend = v.answering_spend;
  }
  return hasDiscoveryValues(out) ? out : undefined;
}

interface DiscoveryPanelProps {
  value: DiscoveryValues;
  onChange: (next: DiscoveryValues) => void;
  compact?: boolean;
}

export function DiscoveryPanel({ value, onChange, compact }: DiscoveryPanelProps) {
  const set = (patch: Partial<DiscoveryValues>) => onChange({ ...value, ...patch });

  return (
    <div className={compact ? 'discovery-panel discovery-panel-compact' : 'discovery-panel'}>
      <label>
        After-hours handling
        <select
          value={value.after_hours || ''}
          onChange={(e) => set({ after_hours: e.target.value || undefined })}
        >
          <option value="">—</option>
          <option value="owner_cell">Owner cell</option>
          <option value="answering_service">Answering service</option>
          <option value="voicemail">Voicemail</option>
          <option value="nobody">Nobody</option>
          <option value="unknown">Unknown</option>
        </select>
      </label>

      <label>
        Current tool
        <input
          type="text"
          placeholder="e.g. Housecall Pro, front desk only"
          value={value.current_tool || ''}
          onChange={(e) => set({ current_tool: e.target.value })}
        />
      </label>

      <label>
        Hiring front desk?
        <select
          value={value.hiring_front_desk == null ? '' : String(value.hiring_front_desk)}
          onChange={(e) => {
            const v = e.target.value;
            set({ hiring_front_desk: v === '' ? null : Number(v) });
          }}
        >
          <option value="">—</option>
          <option value="1">Yes</option>
          <option value="0">No</option>
        </select>
      </label>

      <label>
        Missed-call volume
        <select
          value={value.missed_calls || ''}
          onChange={(e) => set({ missed_calls: e.target.value || undefined })}
        >
          <option value="">—</option>
          <option value="none">None</option>
          <option value="some">Some</option>
          <option value="many">Many</option>
          <option value="unknown">Unknown</option>
        </select>
      </label>

      <label>
        Answering service spend ($/mo)
        <input
          type="number"
          min={0}
          step={50}
          placeholder="0"
          value={value.answering_spend ?? ''}
          onChange={(e) => {
            const raw = e.target.value;
            set({ answering_spend: raw === '' ? null : Number(raw) });
          }}
        />
      </label>
    </div>
  );
}
