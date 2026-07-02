import OptionChainTable from "@/components/option-chain/OptionChainTable";
import type { QqqSpreadAnalysis } from "@/types/qqqSpreadAnalyzer";

type Props = { data: QqqSpreadAnalysis };

export default function OptionChainPanel({ data }: Props) {
  const liquidCount = data.liquid_options?.length ?? 0;
  const rawCount = data.raw_options?.length ?? data.diagnostics.raw_quotes ?? 0;

  return (
    <section className="panel qqq-diag">
      <details>
        <summary>
          Option Chain ({liquidCount} liquid / {rawCount} raw)
        </summary>
        <OptionChainTable
          liquidOptions={data.liquid_options}
          rawOptions={data.raw_options}
          rawCountHint={data.diagnostics.raw_quotes}
          emptyMessage="No option quotes in this snapshot. Run analysis during market hours."
        />
      </details>
    </section>
  );
}
