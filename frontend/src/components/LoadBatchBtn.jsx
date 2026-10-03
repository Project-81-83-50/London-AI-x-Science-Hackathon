function LoadBatchBtn({ batch, selected, onToggle }) {
  return (
    <button
      className="reference-select"
      type="button"
      aria-pressed={selected}
      onClick={() => onToggle(batch)}
    >
      {selected ? "Hide images" : `Load Batch ${batch} images`}
    </button>
  );
}

export default LoadBatchBtn;
